"""Anthropic Messages API (POST /v1/messages). System prompt is top-level; max_tokens required."""
from app.providers.base import ChatRequest, ChatResult, HttpAdapter, ProviderError, ToolCall, group_tool_results

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(HttpAdapter):
    kind = "anthropic"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "https://api.anthropic.com").rstrip("/")

    def _headers(self) -> dict:
        return {"x-api-key": self.cfg.api_key or "", "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json"}

    def build_body(self, req: ChatRequest) -> dict:
        msgs: list[dict] = []
        for m in group_tool_results(req.messages):
            if isinstance(m, list):
                msgs.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": t.tool_call_id, "content": t.content} for t in m]})
            elif m.role == "assistant" and m.tool_calls:
                msgs.append({"role": "assistant", "content": m.raw if m.raw else (
                    ([{"type": "text", "text": m.content}] if m.content else [])
                    + [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls])})
            else:
                msgs.append({"role": m.role, "content": m.content})
        body: dict = {"model": req.model, "max_tokens": req.max_output_tokens, "messages": msgs}
        if req.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                             for t in req.tools]
        if req.system:
            body["system"] = req.system
        if req.temperature is not None:
            body["temperature"] = min(req.temperature, 1.0)  # Anthropic range is 0..1
        if req.top_p is not None:
            body["top_p"] = req.top_p
        return body

    async def chat(self, req: ChatRequest) -> ChatResult:
        data = await self._request("POST", f"{self.base}/v1/messages", headers=self._headers(),
                                   json=self.build_body(req))
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise ProviderError("unknown", "unexpected response shape from provider")
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        calls = [ToolCall(id=b["id"], name=b["name"], arguments=b.get("input") or {})
                 for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        usage = data.get("usage") or {}
        return ChatResult(text=text, input_tokens=int(usage.get("input_tokens") or 0),
                          output_tokens=int(usage.get("output_tokens") or 0),
                          finish_reason=data.get("stop_reason"), provider_request_id=data.get("id"),
                          tool_calls=calls, raw_assistant=blocks if calls else None)

    async def list_models(self) -> list[str]:
        data = await self._request("GET", f"{self.base}/v1/models", headers=self._headers(),
                                   params={"limit": 100})
        return sorted(m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m)
