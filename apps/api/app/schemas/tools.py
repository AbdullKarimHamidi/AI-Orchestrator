from datetime import datetime
from typing import Any, Literal

from pydantic import Field, HttpUrl, field_validator, model_validator

from app.schemas.common import ApiModel, OutModel

TOOL_NAME = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
HEADER_NAME = r"^[A-Za-z0-9-]{1,100}$"


def _object_schema(v: dict | None) -> dict | None:
    if v is not None and v.get("type") not in (None, "object"):
        raise ValueError("input_schema must be a JSON Schema with type 'object'")
    return v


def _headers(v: dict[str, str] | None) -> dict[str, str] | None:
    import re

    for k, val in (v or {}).items():
        if not re.match(HEADER_NAME, k) or len(val) > 4000 or "\n" in val or "\r" in val:
            raise ValueError(f"invalid header {k!r}")
    return v


class HttpToolConfig(ApiModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    url: str = Field(min_length=8, max_length=2000, description="May contain {argument} placeholders")
    timeout_seconds: float | None = Field(default=None, ge=1, le=300)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        HttpUrl(v.replace("{", "x").replace("}", "x"))  # validate shape with placeholders neutralized
        return v


class McpToolConfig(ApiModel):
    server_url: HttpUrl
    tool_name: str = Field(min_length=1, max_length=200)


class ToolCreate(ApiModel):
    name: str = Field(pattern=TOOL_NAME, description="What the model calls it: letters, digits, _ and -")
    description: str = Field(min_length=1, max_length=4000)
    kind: Literal["http", "mcp"]
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    http: HttpToolConfig | None = None
    mcp: McpToolConfig | None = None
    headers: dict[str, str] = Field(default_factory=dict, description="Sent as-is; visible to members")
    secret_headers: dict[str, str] = Field(default_factory=dict, description="Encrypted; never returned")
    enabled: bool = True

    @field_validator("input_schema")
    @classmethod
    def _schema(cls, v: dict | None) -> dict | None:
        return _object_schema(v)

    @field_validator("headers", "secret_headers")
    @classmethod
    def _h(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _headers(v)

    @model_validator(mode="after")
    def _kind_config(self) -> "ToolCreate":
        if self.kind == "http" and not self.http:
            raise ValueError("http tools need an 'http' configuration")
        if self.kind == "mcp" and not self.mcp:
            raise ValueError("mcp tools need an 'mcp' configuration")
        return self


class ToolUpdate(ApiModel):
    name: str | None = Field(default=None, pattern=TOOL_NAME)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    input_schema: dict[str, Any] | None = None
    http: HttpToolConfig | None = None
    mcp: McpToolConfig | None = None
    headers: dict[str, str] | None = None
    secret_headers: dict[str, str] | None = Field(default=None, description="Replaces all secret headers when set")
    enabled: bool | None = None

    @field_validator("input_schema")
    @classmethod
    def _schema(cls, v: dict | None) -> dict | None:
        return _object_schema(v)

    @field_validator("headers", "secret_headers")
    @classmethod
    def _h(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        return _headers(v)


class ToolOut(OutModel):
    id: str
    name: str
    description: str
    kind: Literal["http", "mcp"]
    input_schema: dict[str, Any]
    http: dict | None = None
    mcp: dict | None = None
    headers: dict[str, str]
    secret_header_names: list[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ToolTestRequest(ApiModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolTestOut(OutModel):
    ok: bool
    output: str | None
    error: str | None
    latency_ms: int


class McpDiscoverRequest(ApiModel):
    server_url: HttpUrl
    secret_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("secret_headers")
    @classmethod
    def _h(cls, v: dict[str, str]) -> dict[str, str]:
        return _headers(v) or {}


class McpRemoteTool(OutModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class McpImportRequest(McpDiscoverRequest):
    tools: list[str] = Field(min_length=1, max_length=100)
    name_prefix: str = Field(default="", pattern=r"^[A-Za-z0-9_-]{0,20}$")
