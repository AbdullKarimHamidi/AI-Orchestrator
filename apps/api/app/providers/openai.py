"""OpenAI Chat Completions and OpenAI-compatible endpoints (vLLM, Ollama, LM Studio, etc.)."""
import json

from app.providers.base import ChatRequest, ChatResult, HttpAdapter, ProviderError, ToolCall


class OpenAIAdapter(HttpAdapter):
    kind = "openai"
    default_base = "https://api.openai.com/v1"
    token_param = "max_completion_tokens"  # current OpenAI parameter name

    @property
    def base(self) -> str:
        return (self.cfg.base_url or self.default_base).rstrip("/")

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h

    def build_body(self, req: ChatRequest) -> dict:
        msgs = []
        if req.system:
            msgs.append({"role": "system", "content": req.system})
        for m in req.messages:
            if m.role == "tool":
                msgs.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            elif m.role == "assistant" and m.tool_calls:
                msgs.append({"role": "assistant", "content": m.content or None, "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in m.tool_calls]})
            else:
                msgs.append({"role": m.role, "content": m.content})
        body: dict = {"model": req.model, "messages": msgs, self.token_param: req.max_output_tokens}
        if req.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in req.tools]
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.top_p is not None:
            body["top_p"] = req.top_p
        return body

    async def chat(self, req: ChatRequest) -> ChatResult:
        data = await self._request("POST", f"{self.base}/chat/completions", headers=self._headers(),
                                   json=self.build_body(req))
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            calls = []
            for c in choice["message"].get("tool_calls") or []:
                fn = c["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {"_unparseable_arguments": fn.get("arguments")}
                calls.append(ToolCall(id=c["id"], name=fn["name"], arguments=args if isinstance(args, dict) else {}))
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unknown", "unexpected response shape from provider") from exc
        usage = data.get("usage") or {}
        return ChatResult(text=text, input_tokens=int(usage.get("prompt_tokens") or 0),
                          output_tokens=int(usage.get("completion_tokens") or 0),
                          finish_reason=choice.get("finish_reason"), provider_request_id=data.get("id"),
                          tool_calls=calls)

    async def list_models(self) -> list[str]:
        data = await self._request("GET", f"{self.base}/models", headers=self._headers())
        return sorted(m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m)


class OpenAICompatibleAdapter(OpenAIAdapter):
    kind = "openai_compatible"
    token_param = "max_tokens"  # widely supported by compatible servers
