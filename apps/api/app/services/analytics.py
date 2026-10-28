"""Time series and per-agent / per-workflow breakdowns for the analytics page."""
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.repositories.base import now


async def timeseries(db: AsyncDatabase, ws_id: str, days: int) -> list[dict]:
    """One row per UTC day (oldest first, gaps filled): runs by outcome, tokens and cost."""
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - timedelta(days=days - 1)
    day = {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}
    rows: dict[str, dict] = {}
    async for r in await db["runs"].aggregate([
            {"$match": {"workspace_id": ws_id, "created_at": {"$gte": since}}},
            {"$group": {"_id": {"d": day, "s": "$status"}, "n": {"$sum": 1}}}]):
        row = rows.setdefault(r["_id"]["d"], {"completed": 0, "failed": 0, "other": 0})
        key = r["_id"]["s"] if r["_id"]["s"] in ("completed", "failed") else "other"
        row[key] += r["n"]
    usage: dict[str, dict] = {}
    async for r in await db["usage_records"].aggregate([
            {"$match": {"workspace_id": ws_id, "ts": {"$gte": since}}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
                        "c": {"$sum": "$cost_usd"}, "t": {"$sum": {"$add": ["$input_tokens", "$output_tokens"]}}}}]):
        usage[r["_id"]] = r
    out = []
    for i in range(days):
        d = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        r = rows.get(d, {"completed": 0, "failed": 0, "other": 0})
        u = usage.get(d, {})
        out.append({"date": d, "runs": r["completed"] + r["failed"] + r["other"], "completed": r["completed"],
                    "failed": r["failed"], "other": r["other"], "tokens": int(u.get("t", 0)),
                    "cost_usd": round(float(u.get("c", 0.0)), 6)})
    return out


async def breakdown(db: AsyncDatabase, ws_id: str, days: int) -> list[dict]:
    """Per agent (and per workflow) over the window: volume, success rate, latency and cost."""
    since = now() - timedelta(days=days)
    out = []
    async for r in await db["runs"].aggregate([
            {"$match": {"workspace_id": ws_id, "created_at": {"$gte": since}}},
            {"$group": {
                "_id": {"kind": {"$ifNull": ["$kind", "agent"]},
                        "id": {"$cond": [{"$eq": ["$kind", "workflow"]}, "$workflow_id", "$agent_id"]}},
                "name": {"$last": "$agent_name"}, "runs": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$in": ["$status", ["failed", "timed_out"]]}, 1, 0]}},
                "cost": {"$sum": "$usage.cost_usd"},
                "tokens": {"$sum": {"$add": [{"$ifNull": ["$usage.input_tokens", 0]},
                                             {"$ifNull": ["$usage.output_tokens", 0]}]}},
                "lat": {"$avg": {"$cond": [{"$and": ["$started_at", "$finished_at"]},
                                           {"$dateDiff": {"startDate": "$started_at", "endDate": "$finished_at",
                                                          "unit": "millisecond"}}, None]}}}},
            {"$sort": {"runs": -1}}, {"$limit": 100}]):
        finished = r["completed"] + r["failed"]
        out.append({"kind": r["_id"]["kind"], "id": r["_id"]["id"] or "", "name": r["name"] or "", "runs": r["runs"],
                    "completed": r["completed"], "failed": r["failed"],
                    "success_rate": round(r["completed"] / finished, 4) if finished else None,
                    "avg_latency_ms": int(r["lat"]) if r["lat"] is not None else None,
                    "tokens": int(r["tokens"]), "cost_usd": round(float(r["cost"] or 0.0), 6)})
    return out
