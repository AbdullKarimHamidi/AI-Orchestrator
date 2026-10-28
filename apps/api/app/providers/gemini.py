"""Google Gemini API (generateContent). Uses 'model' role for assistant turns and
systemInstruction for the system prompt; usage in usageMetadata."""
from urllib.parse import quote

from app.providers.base import ChatRequest, ChatResult, HttpAdapter, ProviderError, ToolCall, group_tool_results


class GeminiAdapter(HttpAdapter):
    kind = "gemini"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def _headers(self) -> dict:
        # Key in header (not query string) so it never lands in URL logs.
        return {"x-goog-api-key": self.cfg.api_key or "", "Content-Type": "application/json"}

    def build_body(self, req: ChatRequest) -> dict:
        contents: list[dict] = []
        for m in group_tool_results(req.messages):
            if isinstance(m, list):
                contents.append({"role": "user", "parts": [
                    {"functionResponse": {"name": t.name, "response": {"result": t.content}}} for t in m]})
            elif m.role == "assistant" and m.tool_calls:
                contents.append({"role": "model", "parts": m.raw if m.raw else (
                    ([{"text": m.content}] if m.content else [])
                    + [{"functionCall": {"name": c.name, "args": c.arguments}} for c in m.tool_calls])})
            else:
                contents.append({"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]})
        gen: dict = {"maxOutputTokens": req.max_output_tokens}
        if req.temperature is not None:
            gen["temperature"] = req.temperature
        if req.top_p is not None:
            gen["topP"] = req.top_p
        body: dict = {"contents": contents, "generationConfig": gen}
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        if req.tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parametersJsonSchema": t.parameters}
                for t in req.tools]}]
        return body

    async def chat(self, req: ChatRequest) -> ChatResult:
        model = req.model.removeprefix("models/")
        data = await self._request("POST", f"{self.base}/models/{quote(model, safe='')}:generateContent",
                                   headers=self._headers(), json=self.build_body(req))
        cands = data.get("candidates")
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError("bad_request", f"no candidates returned{f' (blocked: {reason})' if reason else ''}")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        calls = [ToolCall(id=f"call_{i}", name=p["functionCall"]["name"], arguments=p["functionCall"].get("args") or {})
                 for i, p in enumerate(parts) if isinstance(p, dict) and "functionCall" in p]
        usage = data.get("usageMetadata") or {}
        return ChatResult(text=text, input_tokens=int(usage.get("promptTokenCount") or 0),
                          output_tokens=int(usage.get("candidatesTokenCount") or 0),
                          finish_reason=cands[0].get("finishReason"), provider_request_id=data.get("responseId"),
                          tool_calls=calls, raw_assistant=parts if calls else None)

    async def list_models(self) -> list[str]:
        data = await self._request("GET", f"{self.base}/models", headers=self._headers(), params={"pageSize": 200})
        return sorted(m["name"].removeprefix("models/") for m in data.get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or []))
