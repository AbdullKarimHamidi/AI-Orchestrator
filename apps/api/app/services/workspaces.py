from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import Conflict, Forbidden, NotFound
from app.repositories.audit import AuditRepository
from app.repositories.identity import UserRepository, WorkspaceRepository
from app.services.billing import BillingService
from app.services.rbac import ROLE_RANK


class WorkspaceService:
    def __init__(self, db: AsyncDatabase):
        self.ws = WorkspaceRepository(db)
        self.billing = BillingService(db)
        self.users = UserRepository(db)
        self.audit = AuditRepository(db)

    async def members(self, ws_id: str) -> list[dict]:
        ms = await self.ws.members_of(ws_id)
        users = await self.users.many([m["user_id"] for m in ms])
        return [{"user_id": m["user_id"], "email": users[m["user_id"]]["email"],
                 "name": users[m["user_id"]]["name"], "role": m["role"], "joined_at": m["joined_at"]}
                for m in ms if m["user_id"] in users]

    async def add_member(self, ws_id: str, actor: dict, actor_role: str, email: str, role: str) -> None:
        """Adds an existing user. Email-based invitations for non-registered users require an
        outbound email service and are not implemented yet (surfaced as such in the UI)."""
        if ROLE_RANK[role] > ROLE_RANK[actor_role]:
            raise Forbidden("Cannot grant a role higher than your own")
        user = await self.users.by_email(email)
        if not user:
            raise NotFound("No registered user with that email. Ask them to register first.",
                           code="USER_NOT_REGISTERED")
        if await self.ws.membership(ws_id, user["_id"]):
            raise Conflict("User is already a member")
        await self.billing.check_seat(ws_id)
        await self.ws.add_member(ws_id, user["_id"], role)
        await self.audit.record(ws_id, actor["_id"], "member.add", "user", user["_id"], {"role": role})

    async def set_role(self, ws_id: str, actor: dict, actor_role: str, user_id: str, role: str) -> None:
        target = await self.ws.membership(ws_id, user_id)
        if not target:
            raise NotFound("Member not found")
        if ROLE_RANK[role] > ROLE_RANK[actor_role] or ROLE_RANK[target["role"]] > ROLE_RANK[actor_role]:
            raise Forbidden("Cannot change roles at or above your own level")
        if target["role"] == "owner" and role != "owner" and await self.ws.count_owners(ws_id) <= 1:
            raise Conflict("A workspace must keep at least one owner", code="LAST_OWNER")
        await self.ws.set_role(ws_id, user_id, role)
        await self.audit.record(ws_id, actor["_id"], "member.role_change", "user", user_id,
                                {"from": target["role"], "to": role})

    async def remove(self, ws_id: str, actor: dict, actor_role: str, user_id: str) -> None:
        target = await self.ws.membership(ws_id, user_id)
        if not target:
            raise NotFound("Member not found")
        if ROLE_RANK[target["role"]] > ROLE_RANK[actor_role]:
            raise Forbidden("Cannot remove a member with a higher role")
        if target["role"] == "owner" and await self.ws.count_owners(ws_id) <= 1:
            raise Conflict("A workspace must keep at least one owner", code="LAST_OWNER")
        await self.ws.remove_member(ws_id, user_id)
        await self.audit.record(ws_id, actor["_id"], "member.remove", "user", user_id)
