from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, OutModel

SCOPE = r"^[A-Za-z0-9_.:@\-]{1,120}$"


class MemoryCreate(ApiModel):
    agent_id: str = Field(min_length=1, max_length=64)
    scope: str = Field(default="global", pattern=SCOPE,
                       description="'global' (every run) or an end-user / conversation id passed as input.memory_scope")
    content: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    ttl_days: int | None = Field(default=None, ge=1, le=3650, description="Delete automatically after N days")


class MemoryUpdate(ApiModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=10)


class ForgetRequest(ApiModel):
    agent_id: str = Field(min_length=1, max_length=64)
    scope: str | None = Field(default=None, pattern=SCOPE, description="Omit to delete every memory of the agent")


class MemoryOut(OutModel):
    id: str
    agent_id: str
    scope: str
    content: str
    tags: list[str]
    source: Literal["manual", "run"]
    run_id: str | None
    created_by: str
    created_at: datetime
    expires_at: datetime | None


class MemoryScopeOut(OutModel):
    agent_id: str
    scope: str
    count: int
    last_at: datetime


class ForgetResult(OutModel):
    deleted: int
