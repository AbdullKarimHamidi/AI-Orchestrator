from datetime import datetime

from app.core.ids import new_id
from app.core.logging import correlation_id, redact
from app.repositories.base import ScopedRepository, now


class AuditRepository(ScopedRepository):
    collection_name = "audit_logs"

    async def record(self, workspace_id: str | None, actor_id: str | None, action: str,
                     target_type: str | None = None, target_id: str | None = None,
                     details: dict | None = None, ip: str | None = None) -> None:
        await self.col.insert_one({"_id": new_id("aud"), "workspace_id": workspace_id or "-",
                                   "actor_id": actor_id, "action": action, "target_type": target_type,
                                   "target_id": target_id, "details": redact(details or {}), "ip": ip,
                                   "correlation_id": correlation_id.get(), "ts": now()})

    async def list(self, workspace_id: str, filt: dict | None = None, *, sort=None, limit=50, offset=0):
        return await super().list(workspace_id, filt, sort=[("ts", -1)], limit=limit, offset=offset)


class UsageRepository(ScopedRepository):
    collection_name = "usage_records"

    async def record(self, doc: dict) -> None:
        await self.col.insert_one({"_id": new_id("use"), "ts": now(), **doc})

    async def cost_since(self, workspace_id: str, since: datetime) -> float:
        agg = self.col.aggregate([{"$match": {"workspace_id": workspace_id, "ts": {"$gte": since}}},
                                  {"$group": {"_id": None, "c": {"$sum": "$cost_usd"}}}])
        async for row in await agg:
            return float(row["c"])
        return 0.0


class RateLimitRepository:
    """Fixed-window counters in Mongo (TTL-expired). Adequate for login/abuse limits
    without adding Redis; swap for Redis if limits become hot-path per-request."""

    def __init__(self, db):
        self.col = db["rate_limits"]

    async def hit(self, key: str, window_seconds: int) -> int:
        from datetime import timedelta

        t = now()
        bucket = int(t.timestamp()) // window_seconds
        doc = await self.col.find_one_and_update(
            {"_id": f"{key}:{bucket}"},
            {"$inc": {"n": 1}, "$setOnInsert": {"expires_at": t + timedelta(seconds=window_seconds * 2)}},
            upsert=True, return_document=True)
        return int(doc["n"])
