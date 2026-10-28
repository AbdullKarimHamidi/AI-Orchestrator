"""Provider abstraction. Each adapter translates a normalized ChatRequest into the
provider's native wire format; providers do NOT share a request shape.

Adapters perform exactly one HTTP attempt (no hidden retries). Retries and fallbacks
are decided explicitly by the orchestration layer so every attempt is budget-checked
and recorded as usage.
"""
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx

ErrorKind = Literal["auth", "rate_limit", "bad_request", "timeout", "unavailable", "not_found", "unknown"]


@dataclass
class ToolSpec:
    """A function the model may call. ``parameters`` is a JSON Schema object."""
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    """Provider-neutral turn. Assistant turns that requested tools carry ``tool_calls`` and the
    provider-native payload in ``raw`` (echoed back verbatim: Anthropic content blocks, Gemini parts
    with thought signatures). Tool results are ``role="tool"`` with ``tool_call_id`` and ``name``."""
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    raw: Any = None


@dataclass
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    system: str = ""
    max_output_tokens: int = 1024
    temperature: float | None = None
    top_p: float | None = None
    tools: list[ToolSpec] = field(default_factory=list)


@dataclass
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    finish_reason: str | None = None
    provider_request_id: str | None = None
    extra: dict = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_assistant: Any = None  # provider-native assistant message, for the next turn


def group_tool_results(messages: list[ChatMessage]) -> list[list[ChatMessage] | ChatMessage]:
    """Groups consecutive tool-result messages (Anthropic and Gemini send them as one turn)."""
    out: list[list[ChatMessage] | ChatMessage] = []
    for m in messages:
        if m.role == "tool" and out and isinstance(out[-1], list):
            out[-1].append(m)
        elif m.role == "tool":
            out.append([m])
        else:
            out.append(m)
    return out


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str, status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


@dataclass
class ProviderConfig:
    kind: str
    api_key: str | None
    base_url: str | None
    timeout_seconds: float


class ProviderAdapter(Protocol):
    kind: str

    async def chat(self, req: ChatRequest) -> ChatResult: ...

    async def list_models(self) -> list[str]: ...


def classify_status(status: int) -> ErrorKind:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if status in (400, 409, 413, 422):
        return "bad_request"
    if status >= 500:
        return "unavailable"
    return "unknown"


def _safe_error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or err.get("type") or resp.reason_phrase)[:500]
        if isinstance(err, str):
            return err[:500]
    except ValueError:
        pass
    return f"HTTP {resp.status_code} {resp.reason_phrase}"


class HttpAdapter:
    kind = "base"

    def __init__(self, cfg: ProviderConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout_seconds, connect=10.0),
                                 transport=self._transport, follow_redirects=False)

    async def _request(self, method: str, url: str, *, headers: dict, json: dict | None = None,
                       params: dict | None = None) -> dict:
        try:
            async with self._client() as c:
                resp = await c.request(method, url, headers=headers, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", f"provider timed out after {self.cfg.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("unavailable", f"network error: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise ProviderError(classify_status(resp.status_code), _safe_error_message(resp), resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("unknown", "provider returned non-JSON response") from exc
