"""Plans, quotas and monthly usage statements.

This is a self-hosted platform, so there is no payment processor: the plan sets the seat and
monthly run quotas that the API enforces, and its list price is used for internal chargeback
statements (plan fee + model spend recorded in usage_records). Workspaces without a plan are on
``self_hosted``, which has no limits, so existing installs behave exactly as before.
"""
from datetime import UTC, datetime

from pymongo.asynchronous.database import AsyncDatabase

from app.core.exceptions import Conflict, Unprocessable
from app.repositories.audit import AuditRepository
from app.repositories.identity import WorkspaceRepository
from app.services.runs import month_start

PLANS: dict[str, dict] = {
    "self_hosted": {"name": "Self-hosted", "price_usd": 0.0, "seats": None, "runs_per_month": None,
                    "description": "No limits. You run the infrastructure and pay model providers directly."},
    "starter": {"name": "Starter", "price_usd": 0.0, "seats": 3, "runs_per_month": 1_000,
                "description": "For trying the platform with a small team."},
    "team": {"name": "Team", "price_usd": 49.0, "seats": 15, "runs_per_month": 25_000,
             "description": "Shared agents, workflows and evaluations for one team."},
    "business": {"name": "Business", "price_usd": 299.0, "seats": 100, "runs_per_month": 250_000,
                 "description": "Several teams with production traffic and audit requirements."},
}
DEFAULT_PLAN = "self_hosted"


def _next_month(t: datetime) -> datetime:
    return t.replace(year=t.year + 1, month=1) if t.month == 12 else t.replace(month=t.month + 1)


def _prev_month(t: datetime) -> datetime:
    return t.replace(year=t.year - 1, month=12) if t.month == 1 else t.replace(month=t.month - 1)


class BillingService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.ws = WorkspaceRepository(db)
        self.audit = AuditRepository(db)

    async def plan_id(self, ws_id: str) -> str:
        ws = await self.ws.get(ws_id)
        p = ((ws or {}).get("settings") or {}).get("plan") or DEFAULT_PLAN
        return p if p in PLANS else DEFAULT_PLAN

    async def runs_this_month(self, ws_id: str) -> int:
        return await self.db["runs"].count_documents({"workspace_id": ws_id, "created_at": {"$gte": month_start()}})

    async def seats_used(self, ws_id: str) -> int:
        members = await self.db["workspace_members"].count_documents({"workspace_id": ws_id})
        pending = await self.db["invitations"].count_documents({"workspace_id": ws_id, "status": "pending",
                                                                "expires_at": {"$gt": datetime.now(UTC)}})
        return members + pending

    async def check_run_quota(self, ws_id: str) -> None:
        limit = PLANS[await self.plan_id(ws_id)]["runs_per_month"]
        if limit is not None and await self.runs_this_month(ws_id) >= limit:
            raise Conflict(f"The plan's quota of {limit:,} runs this month is used up", code="RUN_QUOTA_EXCEEDED",
                           details={"runs_per_month": limit})

    async def check_seat(self, ws_id: str) -> None:
        plan = PLANS[await self.plan_id(ws_id)]
        if plan["seats"] is not None and await self.seats_used(ws_id) >= plan["seats"]:
            raise Conflict(f"The {plan['name']} plan includes {plan['seats']} seats (members + pending invitations)",
                           code="SEAT_LIMIT", details={"seats": plan["seats"]})

    async def overview(self, ws_id: str) -> dict:
        ws = await self.ws.get(ws_id)
        pid = await self.plan_id(ws_id)
        start = month_start()
        cost = 0.0
        async for row in await self.db["usage_records"].aggregate([
                {"$match": {"workspace_id": ws_id, "ts": {"$gte": start}}},
                {"$group": {"_id": None, "c": {"$sum": "$cost_usd"}}}]):
            cost = float(row["c"])
        return {"plan": {"id": pid, **PLANS[pid]}, "plans": [{"id": k, **v} for k, v in PLANS.items()],
                "period_start": start, "period_end": _next_month(start),
                "runs_used": await self.runs_this_month(ws_id), "seats_used": await self.seats_used(ws_id),
                "model_cost_usd": round(cost, 6),
                "monthly_budget_usd": ((ws or {}).get("settings") or {}).get("monthly_budget_usd"),
                "plan_changed_at": ((ws or {}).get("settings") or {}).get("plan_changed_at")}

    async def change_plan(self, ws_id: str, user_id: str, plan: str) -> dict:
        if plan not in PLANS:
            raise Unprocessable(f"Unknown plan '{plan}'", code="UNKNOWN_PLAN")
        limits = PLANS[plan]
        if limits["seats"] is not None and await self.seats_used(ws_id) > limits["seats"]:
            raise Conflict(f"This workspace uses more than the {limits['seats']} seats of the {limits['name']} plan",
                           code="SEAT_LIMIT")
        old = await self.plan_id(ws_id)
        await self.ws.update(ws_id, {"settings.plan": plan, "settings.plan_changed_at": datetime.now(UTC)})
        await self.audit.record(ws_id, user_id, "billing.plan_change", "workspace", ws_id, {"from": old, "to": plan})
        return await self.overview(ws_id)

    async def statements(self, ws_id: str, months: int) -> list[dict]:
        """One statement per calendar month (newest first): runs, tokens, model spend and the fee of
        the current plan. Months are UTC calendar months."""
        plan = PLANS[await self.plan_id(ws_id)]
        start = month_start()
        for _ in range(months - 1):
            start = _prev_month(start)
        usage: dict[str, dict] = {}
        async for row in await self.db["usage_records"].aggregate([
                {"$match": {"workspace_id": ws_id, "ts": {"$gte": start}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$ts"}},
                            "cost": {"$sum": "$cost_usd"}, "i": {"$sum": "$input_tokens"},
                            "o": {"$sum": "$output_tokens"}, "calls": {"$sum": 1}}}]):
            usage[row["_id"]] = row
        runs: dict[str, int] = {}
        async for row in await self.db["runs"].aggregate([
                {"$match": {"workspace_id": ws_id, "created_at": {"$gte": start}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m", "date": "$created_at"}}, "n": {"$sum": 1}}}]):
            runs[row["_id"]] = row["n"]
        out = []
        cur = month_start()
        for _ in range(months):
            key = cur.strftime("%Y-%m")
            u = usage.get(key, {})
            model_cost = round(float(u.get("cost", 0.0)), 6)
            out.append({"period": key, "period_start": cur, "period_end": _next_month(cur),
                        "current": cur == month_start(), "runs": runs.get(key, 0),
                        "model_calls": int(u.get("calls", 0)),
                        "input_tokens": int(u.get("i", 0)), "output_tokens": int(u.get("o", 0)),
                        "model_cost_usd": model_cost, "plan_fee_usd": plan["price_usd"],
                        "total_usd": round(model_cost + plan["price_usd"], 6)})
            cur = _prev_month(cur)
        return out
