from datetime import datetime
from typing import Literal

from app.schemas.common import ApiModel, OutModel

PlanId = Literal["self_hosted", "starter", "team", "business"]


class Plan(OutModel):
    id: PlanId
    name: str
    price_usd: float
    seats: int | None
    runs_per_month: int | None
    description: str


class BillingOut(OutModel):
    plan: Plan
    plans: list[Plan]
    period_start: datetime
    period_end: datetime
    runs_used: int
    seats_used: int
    model_cost_usd: float
    monthly_budget_usd: float | None
    plan_changed_at: datetime | None


class PlanChange(ApiModel):
    plan: PlanId


class StatementOut(OutModel):
    period: str
    period_start: datetime
    period_end: datetime
    current: bool
    runs: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    model_cost_usd: float
    plan_fee_usd: float
    total_usd: float


class TimeseriesRow(OutModel):
    date: str
    runs: int
    completed: int
    failed: int
    other: int
    tokens: int
    cost_usd: float


class AgentBreakdownRow(OutModel):
    kind: Literal["agent", "workflow"]
    id: str
    name: str
    runs: int
    completed: int
    failed: int
    success_rate: float | None
    avg_latency_ms: int | None
    tokens: int
    cost_usd: float
