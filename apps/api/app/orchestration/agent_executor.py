"""Executes a single agent run: knowledge retrieval, explicit model + fallback chain, tool loop.

- Knowledge: when the agent has knowledge bases, the top-k passages for the user message are
  added to the system prompt as numbered sources and returned as ``output.citations``.
- Tools: the model may call the agent's allowlisted tools; every call is schema-validated,
  executed, and recorded (``tool.call`` / ``tool.result``), up to ``limits.max_tool_calls``.
  The fallback chain applies to the first model call; later turns stay on the provider that
  answered, because a conversation with tool results cannot move between providers.
- One HTTP attempt per chain entry (adapters never retry internally). The project rule
  "gateway auto-retries disabled for budgeted calls" holds: every attempt is visible,
  budget-checked beforehand, and recorded as a usage record afterwards.
- Cancellation/timeout are applied by the worker supervisor cancelling this coroutine;
  asyncio cancellation propagates into the in-flight httpx request and closes it.
"""
import json
import time
from dataclasses import dataclass

import jsonschema
from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import redact, redact_text
from app.providers.base import ChatMessage, ChatRequest, ChatResult, ProviderError, ToolSpec
from app.providers.pricing import estimate_cost
from app.providers.registry import build_adapter
from app.repositories.audit import UsageRepository
from app.repositories.providers import ProviderRepository
from app.repositories.runs import RunEventRepository
from app.repositories.tools import ToolRepository
from app.services.knowledge import KnowledgeService
from app.services.providers import runtime_config
from app.services.runs import BudgetService
from app.services.tools import execute_tool
from app.tools.http_tool import ToolExecutionError

CONTEXT_INSTRUCTIONS = ("Use the retrieved context below when it is relevant. Cite the sources you use as [n]. "
                        "If the context does not contain the answer, say so instead of guessing.")


class RunFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExecutionResult:
    output: dict
    usage: dict
    demo: bool


def _extract_json(text: str) -> object:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object found")
    return json.loads(t[start:t.rfind("}" if t[start] == "{" else "]") + 1])


class AgentExecutor:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.providers = ProviderRepository(db)
        self.events = RunEventRepository(db)
        self.usage = UsageRepository(db)
        self.budget = BudgetService(db)
        self.tools = ToolRepository(db)

    async def _retrieve(self, run: dict, cfg: dict) -> tuple[str, list[dict]]:
        kb_ids = cfg.get("knowledge_base_ids") or []
        system = cfg.get("system_prompt", "")
        if not kb_ids:
            return system, []
        ws, run_id = run["workspace_id"], run["_id"]
        try:
            hits = await KnowledgeService(self.db).search(ws, kb_ids, run["input"]["message"],
                                                          int(cfg.get("knowledge_top_k") or 5))
        except ProviderError as exc:
            raise RunFailure("KNOWLEDGE_UNAVAILABLE", redact_text(f"knowledge search failed: {exc.message}")) from exc
        await self.events.append(run_id, ws, "knowledge.retrieved", {
            "count": len(hits), "sources": [{"n": i + 1, "title": h["title"], "doc_id": h["doc_id"],
                                             "score": h["score"]} for i, h in enumerate(hits)]})
        if not hits:
            return system, []
        ctx = "\n\n".join(f"[{i + 1}] {h['title']}\n{h['text']}" for i, h in enumerate(hits))
        system = f"{system}\n\n{CONTEXT_INSTRUCTIONS}\n<context>\n{ctx}\n</context>".strip()
        citations = [{"n": i + 1, "kb_id": h["kb_id"], "doc_id": h["doc_id"], "title": h["title"],
                      "chunk": h["chunk"], "score": h["score"], "excerpt": h["text"][:300]} for i, h in enumerate(hits)]
        return system, citations

    async def _call(self, run: dict, p: dict, model: str, label: str, req: ChatRequest,
                    totals: dict, per_run_cap: float | None, will_fallback: bool = False) -> ChatResult:
        """One budget-checked, recorded model call. Raises ProviderError on failure."""
        ws, run_id = run["workspace_id"], run["_id"]
        remaining = await self.budget.remaining(ws)
        if remaining is not None and remaining <= 0:
            raise RunFailure("BUDGET_EXCEEDED", "workspace monthly budget exhausted")
        if per_run_cap is not None and totals["cost_usd"] >= per_run_cap:
            raise RunFailure("BUDGET_EXCEEDED", f"per-run cost cap ${per_run_cap} reached")
        await self.events.append(run_id, ws, "model.request", {
            "slot": label, "provider_id": p["_id"], "provider_kind": p["kind"], "model": model,
            "max_output_tokens": req.max_output_tokens, "tools": [t.name for t in req.tools],
            "turn": sum(1 for m in req.messages if m.role == "assistant") + 1})
        started = time.monotonic()
        result: ChatResult | None = None
        err: ProviderError | None = None
        try:
            result = await build_adapter(runtime_config(p)).chat(req)
        except ProviderError as exc:
            err = exc
        except ValueError as exc:  # credential decrypt failure
            err = ProviderError("auth", str(exc))
        latency = int((time.monotonic() - started) * 1000)
        in_t = result.input_tokens if result else 0
        out_t = result.output_tokens if result else 0
        cost, priced = estimate_cost(model, in_t, out_t, p.get("pricing"))
        await self.usage.record({"workspace_id": ws, "run_id": run_id, "agent_id": run["agent_id"],
                                 "provider_id": p["_id"], "provider_kind": p["kind"], "model": model,
                                 "input_tokens": in_t, "output_tokens": out_t, "cost_usd": cost,
                                 "priced": priced, "status": "error" if err else "ok", "latency_ms": latency,
                                 "demo": p["kind"] == "demo", "attempt": run.get("attempt", 1)})
        totals["input_tokens"] += in_t
        totals["output_tokens"] += out_t
        totals["cost_usd"] = round(totals["cost_usd"] + cost, 8)
        if err is not None:
            await self.events.append(run_id, ws, "model.error", redact({
                "slot": label, "kind": err.kind, "status": err.status, "message": err.message,
                "latency_ms": latency, "will_fallback": will_fallback}))
            raise err
        assert result is not None
        await self.events.append(run_id, ws, "model.response", {
            "slot": label, "model": model, "latency_ms": latency, "input_tokens": in_t, "output_tokens": out_t,
            "cost_usd": cost, "priced": priced, "finish_reason": result.finish_reason,
            "tool_calls": [c.name for c in result.tool_calls]})
        return result

    async def _run_tools(self, run: dict, calls, by_name: dict[str, dict]) -> list[ChatMessage]:
        ws, run_id = run["workspace_id"], run["_id"]
        out = []
        for call in calls:
            await self.events.append(run_id, ws, "tool.call", redact({
                "tool": call.name, "call_id": call.id, "arguments": call.arguments}))
            started = time.monotonic()
            t = by_name.get(call.name)
            try:
                if t is None:
                    raise ToolExecutionError(f"unknown tool '{call.name}'")
                content, ok = await execute_tool(t, call.arguments), True
            except ToolExecutionError as exc:
                content, ok = f"ERROR: {exc}", False
            content = redact_text(content)
            await self.events.append(run_id, ws, "tool.result", {
                "tool": call.name, "call_id": call.id, "ok": ok,
                "latency_ms": int((time.monotonic() - started) * 1000), "bytes": len(content),
                "preview": content[:500]})
            out.append(ChatMessage("tool", content, tool_call_id=call.id, name=call.name))
        return out

    async def execute(self, run: dict) -> ExecutionResult:
        ws, run_id, cfg = run["workspace_id"], run["_id"], run["config"]
        chain = [cfg["model"], *(cfg.get("fallbacks") or [])]
        params = cfg.get("params") or {}
        limits = cfg.get("limits") or {}
        per_run_cap = limits.get("max_cost_usd_per_run")
        max_tool_calls = int(limits.get("max_tool_calls", 8))
        totals = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

        system, citations = await self._retrieve(run, cfg)
        tool_docs = [t for t in await self.tools.many(ws, list(cfg.get("tool_ids") or [])) if t.get("enabled", True)]
        by_name = {t["name"]: t for t in tool_docs}
        specs = [ToolSpec(t["name"], t["description"], t["input_schema"]) for t in tool_docs] if max_tool_calls else []
        req = ChatRequest(model="", messages=[ChatMessage("user", run["input"]["message"])], system=system,
                          max_output_tokens=int(params.get("max_output_tokens") or 1024),
                          temperature=params.get("temperature"), top_p=params.get("top_p"), tools=specs)

        # First turn: walk the fallback chain.
        last_error: RunFailure | None = None
        chosen: tuple[dict, str, str] | None = None
        result: ChatResult | None = None
        for idx, ref in enumerate(chain):
            label = "primary" if idx == 0 else f"fallback_{idx}"
            p = await self.providers.get(ws, ref["provider_id"])
            if not p or not p.get("enabled", True):
                last_error = RunFailure("PROVIDER_UNAVAILABLE", f"provider {ref['provider_id']} missing or disabled")
                await self.events.append(run_id, ws, "model.skipped", {"slot": label, "reason": last_error.message})
                continue
            if p.get("allowed_models") and ref["model"] not in p["allowed_models"]:
                last_error = RunFailure("MODEL_NOT_ALLOWED", f"model {ref['model']} not allowed on {p['name']}")
                await self.events.append(run_id, ws, "model.skipped", {"slot": label, "reason": last_error.message})
                continue
            req.model = ref["model"]
            try:
                result = await self._call(run, p, ref["model"], label, req, totals, per_run_cap,
                                          will_fallback=idx < len(chain) - 1)
            except ProviderError as err:
                last_error = RunFailure(f"PROVIDER_{err.kind.upper()}", redact_text(err.message))
                continue
            chosen = (p, ref["model"], label)
            break
        if chosen is None or result is None:
            raise last_error or RunFailure("NO_PROVIDER", "no provider in the chain could be used")
        p, model, label = chosen

        # Tool loop on the provider that answered.
        used = 0
        while result.tool_calls:
            req.messages.append(ChatMessage("assistant", result.text, tool_calls=result.tool_calls,
                                            raw=result.raw_assistant))
            req.messages += await self._run_tools(run, result.tool_calls, by_name)
            used += len(result.tool_calls)
            if used >= max_tool_calls:
                req.tools = []  # budget spent: the next answer must be final
                await self.events.append(run_id, ws, "tool.limit_reached", {"max_tool_calls": max_tool_calls})
            try:
                result = await self._call(run, p, model, label, req, totals, per_run_cap)
            except ProviderError as err:
                raise RunFailure(f"PROVIDER_{err.kind.upper()}", redact_text(err.message)) from err
            if not req.tools and result.tool_calls:
                raise RunFailure("TOOL_LIMIT", f"model kept calling tools after the limit of {max_tool_calls}")

        output: dict = {"text": result.text, "model": model, "provider_id": p["_id"], "provider_kind": p["kind"],
                        "slot": label, "tool_calls": used}
        if citations:
            output["citations"] = citations
        if cfg.get("output_schema"):
            try:
                parsed = _extract_json(result.text)
                jsonschema.validate(parsed, cfg["output_schema"])
                output["structured"] = parsed
            except (ValueError, jsonschema.ValidationError) as exc:
                msg = exc.message if isinstance(exc, jsonschema.ValidationError) else str(exc)
                raise RunFailure("OUTPUT_SCHEMA_MISMATCH", f"model output failed schema validation: {msg}") from exc
        return ExecutionResult(output=output, usage=totals, demo=p["kind"] == "demo")
