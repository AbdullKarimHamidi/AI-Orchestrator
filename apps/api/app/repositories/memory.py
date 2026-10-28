from app.repositories.base import ScopedRepository


class MemoryRepository(ScopedRepository):
    collection_name = "memories"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def recent(self, workspace_id: str, agent_id: str, scopes: list[str], limit: int) -> list[dict]:
        """Newest first, for prompt assembly. Expired entries are removed by the TTL index."""
        q = {"workspace_id": workspace_id, "agent_id": agent_id, "scope": {"$in": scopes}}
        return [d async for d in self.col.find(q).sort("created_at", -1).limit(limit)]

    async def scopes(self, workspace_id: str, agent_id: str | None) -> list[dict]:
        match: dict = {"workspace_id": workspace_id}
        if agent_id:
            match["agent_id"] = agent_id
        rows = await self.col.aggregate([
            {"$match": match},
            {"$group": {"_id": {"agent_id": "$agent_id", "scope": "$scope"}, "count": {"$sum": 1},
                        "last_at": {"$max": "$created_at"}}},
            {"$sort": {"last_at": -1}}, {"$limit": 500}])
        return [{"agent_id": r["_id"]["agent_id"], "scope": r["_id"]["scope"], "count": r["count"],
                 "last_at": r["last_at"]} async for r in rows]

    async def delete_scope(self, workspace_id: str, agent_id: str, scope: str | None) -> int:
        q = {"workspace_id": workspace_id, "agent_id": agent_id}
        if scope is not None:
            q["scope"] = scope
        return (await self.col.delete_many(q)).deleted_count
