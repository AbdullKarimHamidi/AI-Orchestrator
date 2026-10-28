from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase

from app.repositories.base import now


class UserRepository:
    def __init__(self, db: AsyncDatabase):
        self.col = db["users"]

    async def by_email(self, email: str) -> dict | None:
        return await self.col.find_one({"email": email.lower()})

    async def get(self, user_id: str) -> dict | None:
        return await self.col.find_one({"_id": user_id})

    async def insert(self, doc: dict, session=None) -> None:
        await self.col.insert_one(doc, session=session)

    async def set_password(self, user_id: str, password_hash: str) -> bool:
        r = await self.col.update_one({"_id": user_id}, {"$set": {"password_hash": password_hash,
                                                                 "password_changed_at": now()}})
        return r.matched_count == 1

    async def many(self, ids: list[str]) -> dict[str, dict]:
        return {u["_id"]: u async for u in self.col.find({"_id": {"$in": ids}})}


class WorkspaceRepository:
    def __init__(self, db: AsyncDatabase):
        self.col = db["workspaces"]
        self.members = db["workspace_members"]

    async def insert(self, doc: dict, session=None) -> None:
        await self.col.insert_one(doc, session=session)

    async def get(self, ws_id: str) -> dict | None:
        return await self.col.find_one({"_id": ws_id})

    async def update(self, ws_id: str, fields: dict) -> None:
        await self.col.update_one({"_id": ws_id}, {"$set": {**fields, "updated_at": now()}})

    async def add_member(self, ws_id: str, user_id: str, role: str, session=None) -> None:
        await self.members.insert_one({"workspace_id": ws_id, "user_id": user_id, "role": role,
                                       "joined_at": now()}, session=session)

    async def membership(self, ws_id: str, user_id: str) -> dict | None:
        return await self.members.find_one({"workspace_id": ws_id, "user_id": user_id})

    async def memberships_for(self, user_id: str) -> list[dict]:
        return [m async for m in self.members.find({"user_id": user_id}).sort("joined_at", 1)]

    async def members_of(self, ws_id: str) -> list[dict]:
        return [m async for m in self.members.find({"workspace_id": ws_id}).sort("joined_at", 1)]

    async def set_role(self, ws_id: str, user_id: str, role: str) -> bool:
        r = await self.members.update_one({"workspace_id": ws_id, "user_id": user_id}, {"$set": {"role": role}})
        return r.matched_count == 1

    async def remove_member(self, ws_id: str, user_id: str) -> bool:
        r = await self.members.delete_one({"workspace_id": ws_id, "user_id": user_id})
        return r.deleted_count == 1

    async def count_owners(self, ws_id: str) -> int:
        return await self.members.count_documents({"workspace_id": ws_id, "role": "owner"})


class SessionRepository:
    def __init__(self, db: AsyncDatabase):
        self.col = db["sessions"]

    async def create(self, token_hash: str, user_id: str, expires_at: datetime, meta: dict) -> None:
        await self.col.insert_one({"_id": token_hash, "user_id": user_id, "created_at": now(),
                                   "expires_at": expires_at, **meta})

    async def get_valid(self, token_hash: str) -> dict | None:
        return await self.col.find_one({"_id": token_hash, "expires_at": {"$gt": now()}})

    async def delete(self, token_hash: str) -> None:
        await self.col.delete_one({"_id": token_hash})

    async def delete_for_user(self, user_id: str, except_id: str | None = None) -> None:
        q: dict = {"user_id": user_id}
        if except_id:
            q["_id"] = {"$ne": except_id}
        await self.col.delete_many(q)
