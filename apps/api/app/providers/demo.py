"""Demo provider: deterministic, offline, zero-cost. Output is always prefixed with
[DEMO] and runs using it are flagged demo=true so they are never mistaken for real
model output or production metrics."""
import asyncio
import hashlib

from app.providers.base import ChatRequest, ChatResult, ProviderConfig

DEMO_MODELS = ["demo-echo", "demo-tools", "demo-slow", "demo-fail"]


class DemoAdapter:
    kind = "demo"

    def __init__(self, cfg: ProviderConfig | None = None, transport: object = None):
        self.cfg = cfg

    async def chat(self, req: ChatRequest) -> ChatResult:
        from app.providers.base import ProviderError

        last = req.messages[-1].content if req.messages else ""
        if req.model == "demo-tools" and req.tools:
            return self._tool_turn(req)
        if req.model == "demo-fail":
            raise ProviderError("unavailable", "demo-fail model always fails (used to exercise fallbacks)")
        if req.model == "demo-slow":
            # Sleeps in small steps so cancellation and timeouts are observable.
            for _ in range(600):
                await asyncio.sleep(0.1)
        digest = hashlib.sha256(f"{req.system}|{last}".encode()).hexdigest()[:8]
        text = f"[DEMO] Synthetic response (no model was called). Echo: {last[:500]} (digest {digest})"
        if "<context>" in req.system:
            ctx = req.system.split("<context>", 1)[1].split("</context>", 1)[0].strip()
            text += f" Retrieved context: {ctx[:300]}"
        return ChatResult(text=text, input_tokens=max(1, len(req.system + last) // 4),
                          output_tokens=max(1, len(text) // 4), finish_reason="stop",
                          provider_request_id=f"demo-{digest}")

    def _tool_turn(self, req: ChatRequest) -> ChatResult:
        """demo-tools: first calls every available tool once (string arguments filled with the user
        message), then answers with what the tools returned. Exercises the full tool loop offline."""
        from app.providers.base import ToolCall

        results = [m for m in req.messages if m.role == "tool"]
        question = next((m.content for m in req.messages if m.role == "user"), "")
        if not results:
            calls = []
            for i, t in enumerate(req.tools):
                props = (t.parameters or {}).get("properties") or {}
                args = {k: question[:200] for k, v in props.items()
                        if isinstance(v, dict) and v.get("type", "string") == "string"}
                calls.append(ToolCall(id=f"demo_call_{i}", name=t.name, arguments=args))
            return ChatResult(text="", input_tokens=max(1, len(question) // 4), output_tokens=len(calls) * 8,
                              finish_reason="tool_calls", provider_request_id="demo-tools", tool_calls=calls)
        summary = "; ".join(f"{m.name} -> {m.content[:300]}" for m in results)
        text = f"[DEMO] Synthetic answer from tool results (no model was called). {summary}"
        return ChatResult(text=text, input_tokens=max(1, len(summary) // 4), output_tokens=max(1, len(text) // 4),
                          finish_reason="stop", provider_request_id="demo-tools")

    async def list_models(self) -> list[str]:
        return list(DEMO_MODELS)
