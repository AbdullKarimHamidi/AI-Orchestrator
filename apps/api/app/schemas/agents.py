from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiModel, OutModel

AgentStatus = Literal["draft", "published", "paused", "retired"]


class ModelRef(ApiModel):
    provider_id: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)


class ModelParams(ApiModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    max_output_tokens: int = Field(default=1024, ge=1, le=64_000)


class AgentLimits(ApiModel):
    timeout_seconds: int = Field(default=120, ge=5, le=900)
    max_cost_usd_per_run: float | None = Field(default=None, ge=0, le=1000)
    max_tool_calls: int = Field(default=8, ge=0, le=50, description="Tool calls allowed per run")


class MemoryConfig(ApiModel):
    enabled: bool = Field(default=False, description="Add stored memories for the run's scope to the prompt")
    top_k: int = Field(default=10, ge=1, le=50, description="Most recent memories added per run")
    save_conversations: bool = Field(default=False, description="Store each completed exchange as a memory")


class AgentConfig(ApiModel):
    system_prompt: str = Field(default="", max_length=50_000)
    model: ModelRef | None = None
    fallbacks: list[ModelRef] = Field(default_factory=list, max_length=3)
    params: ModelParams = Field(default_factory=ModelParams)
    # Tools the model may call (allowlist) and knowledge bases searched before every answer.
    tool_ids: list[str] = Field(default_factory=list, max_length=50)
    knowledge_base_ids: list[str] = Field(default_factory=list, max_length=20)
    knowledge_top_k: int = Field(default=5, ge=1, le=20, description="Passages retrieved per run")
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    limits: AgentLimits = Field(default_factory=AgentLimits)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    @field_validator("input_schema", "output_schema")
    @classmethod
    def _object_schema(cls, v: dict | None) -> dict | None:
        if v is not None and v.get("type") not in (None, "object"):
            raise ValueError("schema must be a JSON Schema with type 'object'")
        return v


class AgentCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    config: AgentConfig = Field(default_factory=AgentConfig)


class AgentUpdate(ApiModel):
    revision: int = Field(description="Optimistic concurrency token from the last read")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    config: AgentConfig | None = None


class AgentOut(OutModel):
    id: str
    workspace_id: str
    name: str
    description: str
    status: AgentStatus
    draft: AgentConfig
    revision: int
    published_version: int | None
    latest_version: int | None
    draft_dirty: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class AgentVersionOut(OutModel):
    id: str
    agent_id: str
    version: int
    config: AgentConfig
    config_hash: str
    note: str
    created_by: str
    created_at: datetime


class PublishRequest(ApiModel):
    note: str = Field(default="", max_length=500)


class RollbackRequest(ApiModel):
    version: int = Field(ge=1)


class CloneRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class VersionDiff(OutModel):
    from_version: int
    to_version: int
    changes: list[dict[str, Any]]
