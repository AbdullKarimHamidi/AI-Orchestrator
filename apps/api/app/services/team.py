"""Team onboarding and programmatic access.

Invitations: an administrator creates a single-use link for an email address and role. No
outbound email is required: the link is shown once to the inviter, who shares it. The invitee
either registers with it (joining the inviting workspace instead of creating one) or, if they
already have an account with that email, accepts it while signed in.

API keys: workspace-scoped bearer tokens (``Authorization: Bearer orch_...``) with a role no
higher than their creator's. Only the SHA-256 is stored; the plaintext is shown once.
"""
import secrets
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.ids import new_id
from app.core.security import hash_token
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.identity import UserRepository, WorkspaceRepository
from app.repositories.team import ApiKeyRepository, InvitationRepository
from app.services.rbac import ROLE_RANK

API_KEY_PREFIX = "orch_"


def present_invitation(i: dict) -> dict:
    return {"id": i["_id"], "email": i["email"], "role": i["role"], "invited_by": i["invited_by"],
            "created_at": i["created_at"], "expires_at": i["expires_at"]}


def present_api_key(k: dict) -> dict:
    return {"id": k["_id"], "name": k["name"], "role": k["role"], "prefix": k["prefix"],
            "created_by": k["created_by"], "created_at": k["created_at"], "last_used_at": k.get("last_used_at"),
            "expires_at": k.get("expires_at")}


class InvitationService:
    def __init__(self, db: AsyncDatabase):
        self.inv = InvitationRepository(db)
        self.ws = WorkspaceRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditRepository(db)

    async def create(self, ws_id: str, actor_id: str, actor_role: str, email: str, role: str) -> dict:
        if ROLE_RANK[role] > ROLE_RANK[actor_role]:
            raise Forbidden("Cannot invite with a role higher than your own")
        email = email.lower()
        existing = await self.users.by_email(email)
        if existing and await self.ws.membership(ws_id, existing["_id"]):
            raise Conflict("That person is already a member", code="ALREADY_MEMBER")
        for p in await self.inv.pending(ws_id):
            if p["email"] == email:
                await self.inv.mark(ws_id, p["_id"], "superseded", actor_id)
        token = secrets.token_urlsafe(32)
        t = now()
        doc = {"_id": new_id("inv"), "workspace_id": ws_id, "email": email, "role": role,
               "token_hash": hash_token(token), "status": "pending", "invited_by": actor_id,
               "created_at": t, "expires_at": t + timedelta(days=get_settings().invitation_ttl_days)}
        await self.inv.insert(doc)
        await self.audit.record(ws_id, actor_id, "invitation.create", "invitation", doc["_id"],
                                {"email": email, "role": role})
        url = f"{get_settings().public_url.rstrip('/')}/invite/{token}"
        return {**present_invitation(doc), "token": token, "url": url}

    async def revoke(self, ws_id: str, actor_id: str, inv_id: str) -> None:
        if not await self.inv.mark(ws_id, inv_id, "revoked", actor_id):
            raise NotFound("Invitation not found")
        await self.audit.record(ws_id, actor_id, "invitation.revoke", "invitation", inv_id)

    async def lookup(self, token: str) -> dict:
        i = await self.inv.by_token_hash(hash_token(token))
        if not i:
            raise NotFound("This invitation link is invalid, expired, or already used", code="INVITATION_INVALID")
        return i

    async def describe(self, token: str) -> dict:
        i = await self.lookup(token)
        ws = await self.ws.get(i["workspace_id"])
        return {"email": i["email"], "role": i["role"], "workspace_name": (ws or {}).get("name", ""),
                "expires_at": i["expires_at"], "has_account": bool(await self.users.by_email(i["email"]))}

    async def accept(self, token: str, user: dict, session=None) -> dict:
        i = await self.lookup(token)
        if i["email"] != user["email"].lower():
            raise Forbidden("This invitation was sent to a different email address", code="INVITATION_EMAIL_MISMATCH")
        if not await self.inv.mark(i["workspace_id"], i["_id"], "accepted", user["_id"], session=session):
            raise NotFound("This invitation was already used", code="INVITATION_INVALID")
        if not await self.ws.membership(i["workspace_id"], user["_id"]):
            await self.ws.add_member(i["workspace_id"], user["_id"], i["role"], session=session)
        await self.audit.record(i["workspace_id"], user["_id"], "invitation.accept", "invitation", i["_id"],
                                {"role": i["role"]})
        return i


class ApiKeyService:
    def __init__(self, db: AsyncDatabase):
        self.keys = ApiKeyRepository(db)
        self.audit = AuditRepository(db)

    async def create(self, ws_id: str, actor: dict, actor_role: str, name: str, role: str,
                     expires_in_days: int | None) -> dict:
        if actor.get("_api_key"):
            raise Forbidden("API keys cannot create other API keys", code="API_KEY_FORBIDDEN")
        if ROLE_RANK[role] > ROLE_RANK[actor_role]:
            raise Forbidden("Cannot create a key with a role higher than your own")
        secret = API_KEY_PREFIX + secrets.token_urlsafe(32)
        t = now()
        doc = {"_id": new_id("key"), "workspace_id": ws_id, "name": name, "role": role,
               "key_hash": hash_token(secret), "prefix": secret[:12], "revoked": False,
               "created_by": actor["_id"], "created_at": t, "last_used_at": None,
               "expires_at": t + timedelta(days=expires_in_days) if expires_in_days else None}
        await self.keys.insert(doc)
        await self.audit.record(ws_id, actor["_id"], "api_key.create", "api_key", doc["_id"],
                                {"name": name, "role": role})
        return {**present_api_key(doc), "key": secret}

    async def revoke(self, ws_id: str, actor_id: str, key_id: str) -> None:
        if not await self.keys.revoke(ws_id, key_id, actor_id):
            raise NotFound("API key not found")
        await self.audit.record(ws_id, actor_id, "api_key.revoke", "api_key", key_id)

    async def resolve(self, secret: str) -> dict | None:
        if not secret.startswith(API_KEY_PREFIX):
            return None
        k = await self.keys.by_hash(hash_token(secret))
        if not k or (k.get("expires_at") and k["expires_at"] <= now()):
            return None
        await self.keys.touch(k["_id"])
        return k
