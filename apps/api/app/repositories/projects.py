from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class ProjectRepository(ScopedRepository):
    collection_name = "projects"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def update_if_revision(self, workspace_id: str, project_id: str, revision: int,
                                 fields: dict) -> dict | None:
        return await self.col.find_one_and_update(
            {"_id": project_id, "workspace_id": workspace_id, "revision": revision, "deleted": False},
            {"$set": {**fields, "updated_at": now()}, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
