"""Google Gemini API using the Interactions REST API.

The Interactions API supports current Gemini models such as gemini-3.8-flash.
Conversation turns and function calls are represented as typed steps so the
provider-neutral agent/tool loop can keep working without server-side state.
"""
from app.providers.base import ChatRequest, ChatResult, HttpAdapter, ProviderError, ToolCall, group_tool_results


class GeminiAdapter(HttpAdapter):
    kind = "gemini"

    @property
    def base(self) -> str:
        return (self.cfg.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def _headers(self) -> dict:
        # Keep the key in a header, never in the URL or logs.
        return {"x-goog-api-key": self.cfg.api_key or "", "Content-Type": "application/json"}

    @staticmethod
    def _text_step(kind: str, text: str) -> dict:
        return {"type": kind, "content": [{"type": "text", "text": text}]}

    @staticmethod
    def _generation_config(req: ChatRequest) -> dict:
        config = {"max_output_tokens": req.max_output_tokens}
        if req.temperature is not None:
            config["temperature"] = req.temperature
        if req.top_p is not None:
            config["top_p"] = req.top_p
        return config

    def build_body(self, req: ChatRequest) -> dict:
        steps: list[dict] = []
        for message in group_tool_results(req.messages):
            if isinstance(message, list):
                for tool_result in message:
                    step = {
                        "type": "function_result",
                        "call_id": tool_result.tool_call_id or "",
                        "result": [{"type": "text", "text": tool_result.content}],
                    }
                    if tool_result.name:
                        step["name"] = tool_result.name
                    steps.append(step)
            elif message.role == "assistant" and message.tool_calls:
                if message.content:
                    steps.append(self._text_step("model_output", message.content))
                for call in message.tool_calls:
                    steps.append({
                        "type": "function_call",
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    })
            elif message.role == "assistant":
                if message.content:
                    steps.append(self._text_step("model_output", message.content))
            else:
                steps.append(self._text_step("user_input", message.content))

        body: dict = {
            "model": req.model.removeprefix("models/"),
            "input": steps,
            # The orchestrator already owns conversation history. Avoid storing
            # duplicate user conversations in Google's interaction history.
            "store": False,
            "generation_config": self._generation_config(req),
        }
        if req.system:
            body["system_instruction"] = req.system
        if req.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in req.tools
            ]
        return body

    async def chat(self, req: ChatRequest) -> ChatResult:
        data = await self._request(
            "POST",
            f"{self.base}/interactions",
            headers=self._headers(),
            json=self.build_body(req),
        )
        steps = data.get("steps") or []
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        raw_calls: list[dict] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("type") == "model_output":
                for part in step.get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text") or "")
            elif step.get("type") == "function_call":
                name = step.get("name")
                if name:
                    call = ToolCall(
                        id=str(step.get("id") or f"call_{len(calls)}"),
                        name=name,
                        arguments=step.get("arguments") or {},
                    )
                    calls.append(call)
                    raw_calls.append(step)

        response_text = "".join(text_parts).strip()
        status = data.get("status")
        if status == "failed" and not response_text and not calls:
            error = data.get("error") or {}
            message = error.get("message") if isinstance(error, dict) else None
            raise ProviderError("unknown", str(message or "Gemini interaction failed"))
        if not response_text and not calls:
            raise ProviderError(
                "unknown",
                f"Gemini interaction returned no text or function calls (status: {status or 'unknown'})",
            )

        usage = data.get("usage") or {}
        return ChatResult(
            text=response_text,
            input_tokens=int(usage.get("total_input_tokens") or usage.get("initial_input_tokens") or 0),
            output_tokens=int(usage.get("total_output_tokens") or 0),
            finish_reason=status,
            provider_request_id=data.get("id"),
            tool_calls=calls,
            raw_assistant=raw_calls if calls else None,
        )

    async def list_models(self) -> list[str]:
        data = await self._request(
            "GET", f"{self.base}/models", headers=self._headers(), params={"pageSize": 200}
        )
        # The model catalog remains the Models API; Interactions is the inference API.
        # The Interactions API does not support legacy Gemini 2.x models.
        # Do not offer models in the picker that cannot be invoked by this adapter.
        return sorted(
            name
            for model in data.get("models", [])
            if "generateContent" in (model.get("supportedGenerationMethods") or [])
            for name in [model["name"].removeprefix("models/")]
            if name.startswith("gemini-3.")
        )
