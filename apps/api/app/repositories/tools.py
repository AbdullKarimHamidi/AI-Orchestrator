from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class ToolRepository(ScopedRepository):
    collection_name = "tools"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def get(self, workspace_id: str, _id: str) -> dict | None:
        return await self.col.find_one({"_id": _id, "workspace_id": workspace_id, "deleted": False})

    async def many(self, workspace_id: str, ids: list[str]) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "_id": {"$in": ids}, "deleted": False})]

    async def update(self, workspace_id: str, _id: str, fields: dict) -> dict | None:
        return await self.col.find_one_and_update({"_id": _id, "workspace_id": workspace_id, "deleted": False},
                                                  {"$set": {**fields, "updated_at": now()}},
                                                  return_document=ReturnDocument.AFTER)
