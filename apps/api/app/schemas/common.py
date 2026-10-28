from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

Role = Literal["owner", "administrator", "developer", "operator", "viewer"]


class ApiModel(BaseModel):
    """Request models: unknown fields are rejected."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class OutModel(BaseModel):
    """Response models: only declared fields are serialized; internal fields are dropped."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)
    correlation_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class Timestamps(BaseModel):
    created_at: datetime
    updated_at: datetime | None = None
