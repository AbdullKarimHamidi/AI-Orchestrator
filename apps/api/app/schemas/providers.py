from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.schemas.common import ApiModel, OutModel

ProviderKind = Literal["openai", "anthropic", "gemini", "openai_compatible", "ollama", "demo"]


class ModelPrice(ApiModel):
    input_per_mtok_usd: float = Field(ge=0)
    output_per_mtok_usd: float = Field(ge=0)


class ProviderCreate(ApiModel):
    kind: ProviderKind
    name: str = Field(min_length=1, max_length=80)
    api_key: str | None = Field(default=None, min_length=1, max_length=500, description="Write-only")
    base_url: HttpUrl | None = None
    allowed_models: list[str] = Field(default_factory=list, max_length=200)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    pricing: dict[str, ModelPrice] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> "ProviderCreate":
        if self.kind == "openai_compatible" and not self.base_url:
            raise ValueError("base_url is required for openai_compatible providers")
        if self.kind not in ("demo", "openai_compatible", "ollama") and not self.api_key:
            raise ValueError("api_key is required for this provider kind")
        return self


class ProviderUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    api_key: str | None = Field(default=None, min_length=1, max_length=500, description="Rotate the key")
    base_url: HttpUrl | None = None
    allowed_models: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    enabled: bool | None = None
    pricing: dict[str, ModelPrice] | None = None


class ProviderHealth(OutModel):
    status: Literal["unknown", "healthy", "unhealthy"]
    checked_at: datetime | None = None
    latency_ms: int | None = None
    error: str | None = None


class ProviderOut(OutModel):
    id: str
    kind: ProviderKind
    name: str
    base_url: str | None
    has_api_key: bool
    api_key_last4: str | None
    preset: str | None = None
    suggested_models: list[str] = Field(default_factory=list, description="Model picker suggestions, not enforced")
    allowed_models: list[str]
    timeout_seconds: int
    enabled: bool
    pricing: dict[str, ModelPrice]
    health: ProviderHealth
    created_at: datetime
    updated_at: datetime


class ConnectionTestOut(OutModel):
    ok: bool
    latency_ms: int
    models: list[str]
    error: str | None = None


class ModelTestRequest(ApiModel):
    model: str = Field(min_length=1, max_length=200)


class ModelTestOut(OutModel):
    ok: bool
    latency_ms: int
    response: str | None = None
    error: str | None = None


class PresetOut(OutModel):
    id: str
    name: str
    kind: ProviderKind
    base_url: str | None
    models: list[str]
    signup_url: str
    free_tier: str
    needs_key: bool
    env_var: str
    env_configured: bool
    provider_id: str | None


class PresetAdd(ApiModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=500, description="Write-only")
    base_url: HttpUrl | None = Field(default=None, description="Only for Ollama: where your server runs")
