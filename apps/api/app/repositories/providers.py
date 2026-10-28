from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class ProviderRepository(ScopedRepository):
    collection_name = "model_providers"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def update(self, workspace_id: str, _id: str, fields: dict) -> dict | None:
        return await self.col.find_one_and_update({"_id": _id, "workspace_id": workspace_id},
                                                  {"$set": {**fields, "updated_at": now()}},
                                                  return_document=ReturnDocument.AFTER)

    async def delete(self, workspace_id: str, _id: str) -> bool:
        r = await self.col.delete_one({"_id": _id, "workspace_id": workspace_id})
        return r.deleted_count == 1

    async def by_kind(self, workspace_id: str, kind: str) -> dict | None:
        return await self.col.find_one({"workspace_id": workspace_id, "kind": kind})
