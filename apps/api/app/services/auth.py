import logging
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, Unauthorized
from app.core.ids import new_id
from app.core.security import DUMMY_HASH, hash_password, hash_token, new_session_token, verify_password
from app.db.client import get_client
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.identity import SessionRepository, UserRepository, WorkspaceRepository
from app.schemas.auth import LoginRequest, PasswordChange, RegisterRequest
from app.services.team import InvitationService

log = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.users = UserRepository(db)
        self.ws = WorkspaceRepository(db)
        self.sessions = SessionRepository(db)
        self.audit = AuditRepository(db)

    async def registration_open(self) -> bool:
        """Sign-up is open when allowed by config, or for the very first account (bootstrap)."""
        return get_settings().allow_registration or await self.users.col.estimated_document_count() == 0

    async def register(self, req: RegisterRequest, ip: str | None) -> tuple[dict, str]:
        """Creates the user plus either a new owned workspace or the invited membership,
        atomically (multi-document transaction: the writes are only meaningful together)."""
        invitations = InvitationService(self.db)
        invite = await invitations.lookup(req.invite_token) if req.invite_token else None
        if invite is None and not await self.registration_open():
            raise Forbidden("Registration is closed. Ask an administrator for an invitation.",
                            code="REGISTRATION_CLOSED")
        if invite is not None and invite["email"] != req.email.lower():
            raise Forbidden("This invitation was sent to a different email address", code="INVITATION_EMAIL_MISMATCH")
        t = now()
        user = {"_id": new_id("usr"), "email": req.email.lower(), "name": req.name,
                "password_hash": hash_password(req.password), "created_at": t}
        ws = None
        if invite is None:
            ws = {"_id": new_id("ws"), "name": req.workspace_name, "owner_id": user["_id"], "created_at": t,
                  "settings": {"monthly_budget_usd": None}}
        try:
            async with get_client().start_session() as s:
                async with await s.start_transaction():
                    await self.users.insert(user, session=s)
                    if ws is not None:
                        await self.ws.insert(ws, session=s)
                        await self.ws.add_member(ws["_id"], user["_id"], "owner", session=s)
                    else:
                        await invitations.accept(req.invite_token, user, session=s)  # type: ignore[arg-type]
        except DuplicateKeyError as exc:
            raise Conflict("An account with this email already exists", code="EMAIL_TAKEN") from exc
        audit_ws = ws["_id"] if ws else invite["workspace_id"]  # type: ignore[index]
        await self.audit.record(audit_ws, user["_id"], "auth.register", "user", user["_id"], ip=ip)
        if ws is not None:
            await self.seed_workspace(ws["_id"], user["_id"])
        token = await self._new_session(user["_id"], ip)
        return user, token

    async def create_workspace(self, user: dict, name: str) -> dict:
        t = now()
        ws = {"_id": new_id("ws"), "name": name, "owner_id": user["_id"], "created_at": t,
              "settings": {"monthly_budget_usd": None}}
        async with get_client().start_session() as s:
            async with await s.start_transaction():
                await self.ws.insert(ws, session=s)
                await self.ws.add_member(ws["_id"], user["_id"], "owner", session=s)
        await self.audit.record(ws["_id"], user["_id"], "workspace.create", "workspace", ws["_id"])
        await self.seed_workspace(ws["_id"], user["_id"])
        return ws

    async def seed_workspace(self, ws_id: str, user_id: str) -> None:
        """Gives a new workspace its free providers and starter agents. Best effort: a seeding
        problem must never block sign-up (the pack can be installed later from the Agents page)."""
        if not get_settings().seed_starter_agents:
            return
        from app.services.starter_agents import StarterAgentService

        try:
            await StarterAgentService(self.db).install(ws_id, user_id)
        except Exception:  # noqa: BLE001
            log.exception("starter agent seeding failed for workspace %s", ws_id)

    async def change_password(self, user: dict, req: PasswordChange, current_token: str | None) -> None:
        """Verifies the current password, then signs out every other session of this user."""
        fresh = await self.users.get(user["_id"])
        if not fresh or not verify_password(fresh["password_hash"], req.current_password):
            raise Unauthorized("Current password is incorrect", code="INVALID_CREDENTIALS")
        await self.users.set_password(user["_id"], hash_password(req.new_password))
        keep = hash_token(current_token) if current_token else None
        await self.sessions.delete_for_user(user["_id"], except_id=keep)
        for m in await self.ws.memberships_for(user["_id"]):
            await self.audit.record(m["workspace_id"], user["_id"], "auth.password_change", "user", user["_id"])

    async def login(self, req: LoginRequest, ip: str | None) -> tuple[dict, str]:
        user = await self.users.by_email(req.email)
        ok = verify_password(user["password_hash"] if user else DUMMY_HASH, req.password)
        if not user or not ok:
            await self.audit.record(None, user["_id"] if user else None, "auth.login_failed",
                                    details={"email": req.email.lower()}, ip=ip)
            raise Unauthorized("Invalid email or password", code="INVALID_CREDENTIALS")
        token = await self._new_session(user["_id"], ip)
        for m in await self.ws.memberships_for(user["_id"]):
            await self.audit.record(m["workspace_id"], user["_id"], "auth.login", "user", user["_id"], ip=ip)
            break
        return user, token

    async def _new_session(self, user_id: str, ip: str | None) -> str:
        token = new_session_token()
        exp = now() + timedelta(hours=get_settings().session_ttl_hours)
        await self.sessions.create(hash_token(token), user_id, exp, {"ip": ip})
        return token

    async def logout(self, token: str) -> None:
        await self.sessions.delete(hash_token(token))

    async def resolve(self, token: str | None) -> dict | None:
        if not token:
            return None
        sess = await self.sessions.get_valid(hash_token(token))
        if not sess:
            return None
        return await self.users.get(sess["user_id"])
