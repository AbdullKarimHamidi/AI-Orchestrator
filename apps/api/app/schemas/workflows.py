from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.common import ApiModel, OutModel

WorkflowStatus = Literal["draft", "published", "archived"]
StepType = Literal["agent", "tool", "knowledge", "transform", "condition"]
ConditionOp = Literal["equals", "not_equals", "contains", "not_contains", "regex", "is_empty", "not_empty",
                      "greater_than", "less_than"]
STEP_ID = r"^[a-z][a-z0-9_]{0,39}$"
END = "end"


class Condition(ApiModel):
    left: str = Field(default="{{ last.text }}", max_length=2000, description="Template evaluated at run time")
    op: ConditionOp = "contains"
    right: str = Field(default="", max_length=2000, description="Template or literal compared with `left`")
    case_sensitive: bool = False


class WorkflowStep(ApiModel):
    """One node. Steps run in list order unless `next` (or a condition's on_true/on_false)
    names another step id, or "end". Strings may use templates such as {{ input.message }},
    {{ input.variables.x }}, {{ steps.<id>.text }} and {{ last.text }}."""
    id: str = Field(pattern=STEP_ID)
    type: StepType
    name: str = Field(default="", max_length=120)
    # agent
    agent_id: str | None = Field(default=None, max_length=64)
    message: str = Field(default="{{ input.message }}", max_length=20_000)
    # tool
    tool_id: str | None = Field(default=None, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)
    # knowledge
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=20)
    query: str = Field(default="{{ input.message }}", max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)
    # transform
    template: str = Field(default="", max_length=20_000)
    # condition
    condition: Condition | None = None
    on_true: str | None = Field(default=None, max_length=40)
    on_false: str | None = Field(default=None, max_length=40)
    # routing for non-condition steps (None = the following step)
    next: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _required_fields(self) -> "WorkflowStep":
        if self.type == "agent" and not self.agent_id:
            raise ValueError(f"step '{self.id}': an agent step needs agent_id")
        if self.type == "tool" and not self.tool_id:
            raise ValueError(f"step '{self.id}': a tool step needs tool_id")
        if self.type == "knowledge" and not self.knowledge_base_ids:
            raise ValueError(f"step '{self.id}': a knowledge step needs at least one knowledge base")
        if self.type == "transform" and not self.template.strip():
            raise ValueError(f"step '{self.id}': a transform step needs a template")
        if self.type == "condition" and self.condition is None:
            raise ValueError(f"step '{self.id}': a condition step needs a condition")
        return self


class WorkflowDefinition(ApiModel):
    steps: list[WorkflowStep] = Field(default_factory=list, max_length=50)
    max_step_executions: int = Field(default=50, ge=1, le=500,
                                     description="Loop guard: a run fails once this many steps have executed")

    @model_validator(mode="after")
    def _graph(self) -> "WorkflowDefinition":
        ids = [s.id for s in self.steps]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate step ids: {', '.join(dupes)}")
        if END in ids:
            raise ValueError("'end' is reserved and cannot be a step id")
        known = set(ids) | {END}
        for s in self.steps:
            for field in ("next", "on_true", "on_false"):
                target = getattr(s, field)
                if target is not None and target not in known:
                    raise ValueError(f"step '{s.id}': {field} points to unknown step '{target}'")
        return self


class WorkflowCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    definition: WorkflowDefinition = Field(default_factory=WorkflowDefinition)


class WorkflowUpdate(ApiModel):
    revision: int = Field(description="Optimistic concurrency token from the last read")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    definition: WorkflowDefinition | None = None


class WorkflowPublish(ApiModel):
    note: str = Field(default="", max_length=500)


class WorkflowRunCreate(ApiModel):
    input: dict[str, Any] = Field(description="Must contain 'message' (string); may contain 'variables'")
    source: Literal["published", "draft"] = "published"
    timeout_seconds: int | None = Field(default=None, ge=5, le=900)


class WorkflowOut(OutModel):
    id: str
    workspace_id: str
    name: str
    description: str
    status: WorkflowStatus
    draft: WorkflowDefinition
    revision: int
    published_version: int | None
    latest_version: int | None
    draft_dirty: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class WorkflowVersionOut(OutModel):
    id: str
    workflow_id: str
    version: int
    definition: WorkflowDefinition
    note: str
    created_by: str
    created_at: datetime
