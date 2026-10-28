"""Long-term agent memory.

Memories belong to one agent and one scope: ``global`` (added to every run of the agent) or an
end-user / conversation id that callers pass as ``input.memory_scope``. When an agent's config has
``memory.enabled``, the executor adds the newest ``memory.top_k`` memories of the run's scopes to
the system prompt; with ``memory.save_conversations`` it stores each completed exchange.
Deletion requests ("forget this user") remove a whole scope at once.
"""
import re
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import NotFound
from app.core.ids import new_id
from app.repositories.agents import AgentRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.memory import MemoryRepository

MEMORY_INSTRUCTIONS = "Facts remembered from earlier conversations (newest first). Use them when relevant."


def present_memory(m: dict) -> dict:
    return {**m, "id": m["_id"], "tags": m.get("tags") or [], "run_id": m.get("run_id"),
            "expires_at": m.get("expires_at")}


def scopes_for(run_input: dict) -> list[str]:
    scope = run_input.get("memory_scope")
    return ["global", scope] if isinstance(scope, str) and scope and scope != "global" else ["global"]


class MemoryService:
    def __init__(self, db: AsyncDatabase):
        self.mem = MemoryRepository(db)
        self.agents = AgentRepository(db)
        self.audit = AuditRepository(db)

    async def _agent(self, ws_id: str, agent_id: str) -> dict:
        a = await self.agents.get(ws_id, agent_id)
        if not a:
            raise NotFound("Agent not found")
        return a

    async def find(self, ws_id: str, agent_id: str | None, scope: str | None, q: str | None,
                   limit: int, offset: int) -> tuple[list[dict], int]:
        f: dict = {}
        if agent_id:
            f["agent_id"] = agent_id
        if scope:
            f["scope"] = scope
        if q:
            f["content"] = {"$regex": re.escape(q), "$options": "i"}
        return await self.mem.list(ws_id, f, limit=limit, offset=offset)

    async def create(self, ws_id: str, user_id: str, agent_id: str, scope: str, content: str,
                     tags: list[str], ttl_days: int | None, source: str = "manual", run_id: str | None = None) -> dict:
        await self._agent(ws_id, agent_id)
        t = now()
        doc = {"_id": new_id("mem"), "workspace_id": ws_id, "agent_id": agent_id, "scope": scope,
               "content": content, "tags": [x.strip()[:40] for x in tags if x.strip()], "source": source,
               "run_id": run_id, "created_by": user_id, "created_at": t, "updated_at": t,
               "expires_at": t + timedelta(days=ttl_days) if ttl_days else None}
        await self.mem.insert(doc)
        if source == "manual":
            await self.audit.record(ws_id, user_id, "memory.create", "memory", doc["_id"],
                                    {"agent_id": agent_id, "scope": scope})
        return doc

    async def update(self, ws_id: str, user_id: str, memory_id: str, fields: dict) -> dict:
        if not await self.mem.get(ws_id, memory_id):
            raise NotFound("Memory not found")
        await self.mem.col.update_one({"_id": memory_id, "workspace_id": ws_id},
                                      {"$set": {**fields, "updated_at": now()}})
        await self.audit.record(ws_id, user_id, "memory.update", "memory", memory_id, {"fields": sorted(fields)})
        return await self.mem.get(ws_id, memory_id)  # type: ignore[return-value]

    async def delete(self, ws_id: str, user_id: str, memory_id: str) -> None:
        r = await self.mem.col.delete_one({"_id": memory_id, "workspace_id": ws_id})
        if r.deleted_count == 0:
            raise NotFound("Memory not found")
        await self.audit.record(ws_id, user_id, "memory.delete", "memory", memory_id)

    async def forget(self, ws_id: str, user_id: str, agent_id: str, scope: str | None) -> int:
        await self._agent(ws_id, agent_id)
        n = await self.mem.delete_scope(ws_id, agent_id, scope)
        await self.audit.record(ws_id, user_id, "memory.forget", "agent", agent_id, {"scope": scope, "deleted": n})
        return n
