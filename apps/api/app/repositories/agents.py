from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class AgentRepository(ScopedRepository):
    collection_name = "agents"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def get(self, workspace_id: str, _id: str) -> dict | None:
        return await self.col.find_one({"_id": _id, "workspace_id": workspace_id, "deleted": False})

    async def update_if_revision(self, workspace_id: str, _id: str, revision: int, fields: dict) -> dict | None:
        """Optimistic concurrency: the update applies only if the stored revision matches."""
        return await self.col.find_one_and_update(
            {"_id": _id, "workspace_id": workspace_id, "deleted": False, "revision": revision},
            {"$set": {**fields, "updated_at": now()}, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER)

    async def update(self, workspace_id: str, _id: str, fields: dict) -> dict | None:
        return await self.col.find_one_and_update(
            {"_id": _id, "workspace_id": workspace_id, "deleted": False},
            {"$set": {**fields, "updated_at": now()}, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER)


class AgentVersionRepository(ScopedRepository):
    collection_name = "agent_versions"

    async def insert(self, doc: dict) -> None:
        # Versions are append-only: there is no update method on this repository.
        await self.col.insert_one(doc)

    async def by_number(self, workspace_id: str, agent_id: str, version: int) -> dict | None:
        return await self.col.find_one({"workspace_id": workspace_id, "agent_id": agent_id, "version": version})

    async def latest(self, workspace_id: str, agent_id: str) -> dict | None:
        return await self.col.find_one({"workspace_id": workspace_id, "agent_id": agent_id},
                                       sort=[("version", -1)])

    async def for_agent(self, workspace_id: str, agent_id: str) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "agent_id": agent_id})
                .sort("version", -1)]
