from app.repositories.agents import AgentRepository
from app.repositories.base import ScopedRepository


class WorkflowRepository(AgentRepository):
    """Same lifecycle storage as agents: soft delete, optimistic revision on the draft."""
    collection_name = "workflows"


class WorkflowVersionRepository(ScopedRepository):
    collection_name = "workflow_versions"

    async def insert(self, doc: dict) -> None:
        # Versions are append-only: there is no update method on this repository.
        await self.col.insert_one(doc)

    async def by_number(self, workspace_id: str, workflow_id: str, version: int) -> dict | None:
        return await self.col.find_one({"workspace_id": workspace_id, "workflow_id": workflow_id, "version": version})

    async def latest(self, workspace_id: str, workflow_id: str) -> dict | None:
        return await self.col.find_one({"workspace_id": workspace_id, "workflow_id": workflow_id},
                                       sort=[("version", -1)])

    async def for_workflow(self, workspace_id: str, workflow_id: str) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "workflow_id": workflow_id})
                .sort("version", -1)]
