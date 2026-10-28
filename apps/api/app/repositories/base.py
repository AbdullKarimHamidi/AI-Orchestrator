"""Repository base. Workspace-scoped repositories take workspace_id as a required
argument on every method and always include it in the Mongo filter, so a handler
cannot accidentally read across tenants."""
from datetime import UTC, datetime

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase


def now() -> datetime:
    return datetime.now(UTC)


class ScopedRepository:
    collection_name: str

    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.col: AsyncCollection = db[self.collection_name]

    async def get(self, workspace_id: str, _id: str) -> dict | None:
        return await self.col.find_one({"_id": _id, "workspace_id": workspace_id})

    async def list(self, workspace_id: str, filt: dict | None = None, *, sort: list | None = None,
                   limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        q = {"workspace_id": workspace_id, **(filt or {})}
        total = await self.col.count_documents(q)
        cur = self.col.find(q).sort(sort or [("created_at", -1)]).skip(offset).limit(limit)
        return [d async for d in cur], total
