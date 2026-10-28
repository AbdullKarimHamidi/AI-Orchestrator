from datetime import UTC, datetime, timedelta

import jsonschema
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound, Unprocessable
from app.core.ids import new_id
from app.repositories.agents import AgentRepository, AgentVersionRepository
from app.repositories.audit import AuditRepository, UsageRepository
from app.repositories.base import now
from app.repositories.identity import WorkspaceRepository
from app.repositories.providers import ProviderRepository
from app.repositories.runs import RunEventRepository, RunRepository
from app.schemas.runs import TERMINAL, RunCreate
from app.services.rbac import has_permission

MAX_ATTEMPTS = 2  # one recovery attempt after a lost worker; provider errors are not retried blindly


def month_start(t: datetime | None = None) -> datetime:
    t = t or datetime.now(UTC)
    return t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def present_run(r: dict) -> dict:
    dur = None
    if r.get("started_at") and r.get("finished_at"):
        dur = int((r["finished_at"] - r["started_at"]).total_seconds() * 1000)
    return {"id": r["_id"], "workspace_id": r["workspace_id"], "kind": r.get("kind", "agent"),
            "agent_id": r["agent_id"], "agent_name": r.get("agent_name", ""),
            "agent_version": r.get("agent_version"), "source": r.get("source", "published"),
            "status": r["status"], "demo": r.get("demo", False), "input": r.get("input", {}),
            "output": r.get("output"), "error": r.get("error"),
            "usage": r.get("usage") or {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            "attempt": r.get("attempt", 0), "max_attempts": r.get("max_attempts", MAX_ATTEMPTS),
            "cancel_requested": r.get("cancel_requested", False), "timeout_seconds": r["timeout_seconds"],
            "created_by": r["created_by"], "created_at": r["created_at"], "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"), "duration_ms": dur, "config": r.get("config", {})}


class BudgetService:
    def __init__(self, db: AsyncDatabase):
        self.ws = WorkspaceRepository(db)
        self.usage = UsageRepository(db)

    async def remaining(self, ws_id: str) -> float | None:
        ws = await self.ws.get(ws_id)
        budget = ((ws or {}).get("settings") or {}).get("monthly_budget_usd")
        if budget is None:
            return None
        return float(budget) - await self.usage.cost_since(ws_id, month_start())


class RunService:
    def __init__(self, db: AsyncDatabase):
        self.runs = RunRepository(db)
        self.events = RunEventRepository(db)
        self.agents = AgentRepository(db)
        self.versions = AgentVersionRepository(db)
        self.providers = ProviderRepository(db)
        self.audit = AuditRepository(db)
        self.budget = BudgetService(db)

    async def create(self, ws_id: str, user_id: str, role: str, req: RunCreate,
                     idempotency_key: str | None) -> tuple[dict, bool]:
        agent = await self.agents.get(ws_id, req.agent_id)
        if not agent:
            raise NotFound("Agent not found")
        if req.source == "draft":
            # The test console executes unpublished config: restricted to people who can edit it.
            if not has_permission(role, "agents:write"):
                raise Forbidden("Testing a draft requires the agents:write permission")
            if agent["status"] == "retired":
                raise Conflict("Retired agents cannot run", code="AGENT_RETIRED")
            config, version = agent["draft"], None
        else:
            if agent["status"] != "published" or not agent.get("published_version"):
                raise Conflict(f"Agent is '{agent['status']}' and cannot accept production runs",
                               code="AGENT_NOT_RUNNABLE")
            v = await self.versions.by_number(ws_id, agent["_id"], agent["published_version"])
            if not v:
                raise Conflict("Published version is missing", code="VERSION_MISSING")
            config, version = v["config"], v["version"]
        if not config.get("model"):
            raise Unprocessable("Agent has no model configured", code="MODEL_REQUIRED")
        msg = req.input.get("message")
        if not isinstance(msg, str) or not msg.strip():
            raise Unprocessable("input.message must be a non-empty string", code="INVALID_INPUT")
        if len(msg) > 100_000:
            raise Unprocessable("input.message is too long", code="INVALID_INPUT")
        if config.get("input_schema"):
            try:
                jsonschema.validate(req.input.get("variables", {}), config["input_schema"])
            except jsonschema.ValidationError as exc:
                raise Unprocessable(f"input.variables does not match the agent input schema: {exc.message}",
                                    code="INPUT_SCHEMA_MISMATCH") from exc
        primary = await self.providers.get(ws_id, config["model"]["provider_id"])
        if not primary:
            raise Unprocessable("The agent's primary provider no longer exists", code="PROVIDER_NOT_FOUND")
        remaining = await self.budget.remaining(ws_id)
        if remaining is not None and remaining <= 0:
            raise Conflict("Workspace monthly budget is exhausted", code="BUDGET_EXCEEDED")

        s = get_settings()
        timeout = min(req.timeout_seconds or config.get("limits", {}).get("timeout_seconds")
                      or s.default_run_timeout_seconds, s.max_run_timeout_seconds)
        t = now()
        doc = {"_id": new_id("run"), "workspace_id": ws_id, "kind": "agent", "agent_id": agent["_id"],
               "agent_name": agent["name"], "agent_version": version, "source": req.source, "config": config,
               "input": req.input, "status": "queued", "demo": primary["kind"] == "demo", "output": None,
               "error": None, "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
               "attempt": 0, "max_attempts": MAX_ATTEMPTS, "cancel_requested": False, "timeout_seconds": timeout,
               "deadline_at": None, "available_at": t, "lease_owner": None, "lease_expires_at": None,
               "event_seq": 0, "created_by": user_id, "created_at": t, "updated_at": t}
        if idempotency_key:
            doc["idempotency_key"] = idempotency_key
            run, created = await self.runs.insert_idempotent(doc)
        else:
            run, created = await self.runs.insert(doc), True
        if created:
            await self.events.append(run["_id"], ws_id, "run.queued",
                                     {"agent_version": version, "source": req.source})
            await self.audit.record(ws_id, user_id, "run.create", "run", run["_id"], {"agent_id": agent["_id"]})
        return run, created

    async def get(self, ws_id: str, run_id: str) -> dict:
        r = await self.runs.get(ws_id, run_id)
        if not r:
            raise NotFound("Run not found")
        return r

    async def cancel(self, ws_id: str, user_id: str, run_id: str) -> dict:
        r = await self.get(ws_id, run_id)
        if r["status"] in TERMINAL:
            raise Conflict(f"Run already {r['status']}", code="RUN_TERMINAL")
        updated = await self.runs.request_cancel(ws_id, run_id)
        if updated is None:
            updated = await self.get(ws_id, run_id)
        elif updated["status"] == "cancelled":
            await self.events.append(run_id, ws_id, "run.cancelled", {"phase": "queued"})
        else:
            await self.events.append(run_id, ws_id, "run.cancel_requested", {"by": user_id})
        await self.audit.record(ws_id, user_id, "run.cancel", "run", run_id)
        return updated

    async def list(self, ws_id: str, status: str | None, agent_id: str | None, limit: int, offset: int):
        f: dict = {}
        if status:
            f["status"] = status
        if agent_id:
            f["agent_id"] = agent_id
        return await self.runs.list(ws_id, f, limit=limit, offset=offset)


async def dashboard(db: AsyncDatabase, ws_id: str, days: int) -> dict:
    since = now() - timedelta(days=days)
    runs = db["runs"]
    by_status = {row["_id"]: row["n"] async for row in await runs.aggregate([
        {"$match": {"workspace_id": ws_id, "created_at": {"$gte": since}}},
        {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    lat = [row["d"] async for row in await runs.aggregate([
        {"$match": {"workspace_id": ws_id, "created_at": {"$gte": since}, "status": "completed",
                    "finished_at": {"$ne": None}}},
        {"$project": {"d": {"$dateDiff": {"startDate": "$started_at", "endDate": "$finished_at",
                                          "unit": "millisecond"}}}},
        {"$sort": {"d": 1}}])]

    def pct(p: float) -> int | None:
        return int(lat[min(len(lat) - 1, int(p * len(lat)))]) if lat else None

    usage = {"c": 0.0, "i": 0, "o": 0}
    async for row in await db["usage_records"].aggregate([
            {"$match": {"workspace_id": ws_id, "ts": {"$gte": since}}},
            {"$group": {"_id": None, "c": {"$sum": "$cost_usd"}, "i": {"$sum": "$input_tokens"},
                        "o": {"$sum": "$output_tokens"}}}]):
        usage = row
    finished = sum(by_status.get(k, 0) for k in TERMINAL)
    ws = await db["workspaces"].find_one({"_id": ws_id})
    recent = [r async for r in runs.find({"workspace_id": ws_id}).sort("created_at", -1).limit(8)]
    provs = db["model_providers"]
    return {
        "window_days": days,
        "agents_total": await db["agents"].count_documents({"workspace_id": ws_id, "deleted": False}),
        "agents_published": await db["agents"].count_documents({"workspace_id": ws_id, "deleted": False,
                                                                "status": "published"}),
        "runs_total": sum(by_status.values()), "runs_by_status": by_status,
        "success_rate": round(by_status.get("completed", 0) / finished, 4) if finished else None,
        "p50_latency_ms": pct(0.5), "p95_latency_ms": pct(0.95),
        "cost_usd": round(float(usage["c"]), 6), "input_tokens": int(usage["i"]), "output_tokens": int(usage["o"]),
        "demo_runs": await runs.count_documents({"workspace_id": ws_id, "created_at": {"$gte": since}, "demo": True}),
        "monthly_budget_usd": ((ws or {}).get("settings") or {}).get("monthly_budget_usd"),
        "month_to_date_cost_usd": round(await UsageRepository(db).cost_since(ws_id, month_start()), 6),
        "recent_runs": [present_run(r) for r in recent],
        "providers_total": await provs.count_documents({"workspace_id": ws_id}),
        "providers_unhealthy": await provs.count_documents({"workspace_id": ws_id, "health.status": "unhealthy"}),
    }
