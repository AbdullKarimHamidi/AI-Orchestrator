from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel, OutModel

RunStatus = Literal["queued", "running", "waiting_for_approval", "completed", "failed", "cancelled", "timed_out"]
TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled", "timed_out"})


class RunCreate(ApiModel):
    agent_id: str
    input: dict[str, Any] = Field(description="Must contain 'message' (string); may contain 'variables'")
    source: Literal["published", "draft"] = "published"
    timeout_seconds: int | None = Field(default=None, ge=5, le=900)


class RunUsage(OutModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class RunError(OutModel):
    code: str
    message: str


class RunOut(OutModel):
    id: str
    workspace_id: str
    kind: Literal["agent"]
    agent_id: str
    agent_name: str
    agent_version: int | None
    source: Literal["published", "draft"]
    status: RunStatus
    demo: bool
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: RunError | None
    usage: RunUsage
    attempt: int
    max_attempts: int
    cancel_requested: bool
    timeout_seconds: int
    created_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    config: dict[str, Any]


class RunEventOut(OutModel):
    seq: int
    type: str
    ts: datetime
    data: dict[str, Any]


class DashboardOut(OutModel):
    window_days: int
    agents_total: int
    agents_published: int
    runs_total: int
    runs_by_status: dict[str, int]
    success_rate: float | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    cost_usd: float
    input_tokens: int
    output_tokens: int
    demo_runs: int
    monthly_budget_usd: float | None
    month_to_date_cost_usd: float
    recent_runs: list[RunOut]
    providers_total: int
    providers_unhealthy: int
