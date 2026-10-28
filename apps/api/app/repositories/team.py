from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class InvitationRepository(ScopedRepository):
    """Invitations are stored by the SHA-256 of their token (like sessions): a DB leak does
    not leak usable invitation links."""

    collection_name = "invitations"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def by_token_hash(self, token_hash: str) -> dict | None:
        return await self.col.find_one({"token_hash": token_hash, "status": "pending", "expires_at": {"$gt": now()}})

    async def pending(self, workspace_id: str) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "status": "pending",
                                                "expires_at": {"$gt": now()}}).sort("created_at", -1)]

    async def mark(self, workspace_id: str, _id: str, status: str, by: str | None = None, session=None) -> bool:
        r = await self.col.update_one({"_id": _id, "workspace_id": workspace_id, "status": "pending"},
                                      {"$set": {"status": status, "closed_by": by, "closed_at": now()}},
                                      session=session)
        return r.modified_count == 1


class ApiKeyRepository(ScopedRepository):
    collection_name = "api_keys"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def active(self, workspace_id: str) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "revoked": False})
                .sort("created_at", -1)]

    async def by_hash(self, key_hash: str) -> dict | None:
        return await self.col.find_one({"key_hash": key_hash, "revoked": False})

    async def touch(self, _id: str) -> None:
        await self.col.update_one({"_id": _id}, {"$set": {"last_used_at": now()}})

    async def revoke(self, workspace_id: str, _id: str, by: str) -> dict | None:
        return await self.col.find_one_and_update(
            {"_id": _id, "workspace_id": workspace_id, "revoked": False},
            {"$set": {"revoked": True, "revoked_by": by, "revoked_at": now()}},
            return_document=ReturnDocument.AFTER)
