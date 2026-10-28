from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, OutModel

ScorerType = Literal["exact", "contains", "not_contains", "regex", "json_valid", "not_empty"]


class EvalCase(ApiModel):
    id: str = Field(default="", max_length=40, description="Generated when empty")
    input: str = Field(min_length=1, max_length=20_000, description="Sent as input.message")
    expected: str = Field(default="", max_length=20_000, description="Reference answer / pattern for the scorer")
    variables: dict[str, Any] = Field(default_factory=dict)


class DatasetCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    cases: list[EvalCase] = Field(default_factory=list, max_length=500)


class DatasetUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    cases: list[EvalCase] | None = Field(default=None, max_length=500)


class DatasetOut(OutModel):
    id: str
    name: str
    description: str
    cases: list[EvalCase]
    case_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class Scorer(ApiModel):
    type: ScorerType = "contains"
    case_sensitive: bool = False


class EvalRunCreate(ApiModel):
    dataset_id: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)
    source: Literal["published", "draft"] = "published"
    scorer: Scorer = Field(default_factory=Scorer)
    name: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _default_name(self) -> "EvalRunCreate":
        self.name = self.name.strip()
        return self


class EvalResult(OutModel):
    case_id: str
    input: str
    expected: str
    run_id: str
    status: str
    output: str | None
    passed: bool | None
    reason: str
    latency_ms: int | None
    cost_usd: float


class EvalSummary(OutModel):
    total: int
    finished: int
    passed: int
    failed: int
    errors: int
    pass_rate: float | None
    avg_latency_ms: int | None
    cost_usd: float


class EvalRunOut(OutModel):
    id: str
    name: str
    dataset_id: str
    dataset_name: str
    agent_id: str
    agent_name: str
    agent_version: int | None
    source: Literal["published", "draft"]
    scorer: Scorer
    status: Literal["running", "completed"]
    summary: EvalSummary
    results: list[EvalResult]
    created_by: str
    created_at: datetime
    finished_at: datetime | None


class CompareRow(OutModel):
    case_id: str
    input: str
    expected: str
    a: EvalResult | None
    b: EvalResult | None
    change: Literal["fixed", "regressed", "same_pass", "same_fail", "missing"]


class CompareOut(OutModel):
    a: EvalRunOut
    b: EvalRunOut
    rows: list[CompareRow]
    fixed: int
    regressed: int
