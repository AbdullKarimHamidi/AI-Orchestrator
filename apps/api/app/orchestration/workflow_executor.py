"""Executes a workflow run step by step inside the worker.

- Steps run in list order unless routed with ``next`` / ``on_true`` / ``on_false`` (or "end").
- Agent steps run the agent's *published* version through the regular AgentExecutor, with the
  workflow run as the parent: its model calls, tool calls, usage records and budget checks are
  exactly those of a normal agent run, and its events land in this run's timeline.
- Every step emits ``workflow.step.started`` and ``workflow.step.completed`` (or ``.failed``).
- ``max_step_executions`` bounds loops built with routing, so a cycle cannot run forever.
- Cancellation and timeouts are applied by the worker supervisor cancelling this coroutine.
"""
import json
import re
import time

from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import redact_text
from app.orchestration.agent_executor import AgentExecutor, ExecutionResult, RunFailure
from app.orchestration.templating import TemplateError, render, render_value
from app.providers.base import ProviderError
from app.repositories.agents import AgentRepository, AgentVersionRepository
from app.repositories.runs import RunEventRepository
from app.repositories.tools import ToolRepository
from app.schemas.workflows import END
from app.services.knowledge import KnowledgeService
from app.services.tools import execute_tool
from app.tools.http_tool import ToolExecutionError


def _number(v: str) -> float | None:
    try:
        return float(v.strip())
    except ValueError:
        return None


def evaluate(op: str, left: str, right: str, case_sensitive: bool = False) -> bool:
    """Comparison used by condition steps. Both sides are already-rendered strings."""
    a, b = (left, right) if case_sensitive else (left.lower(), right.lower())
    match op:
        case "equals":
            return a.strip() == b.strip()
        case "not_equals":
            return a.strip() != b.strip()
        case "contains":
            return b in a
        case "not_contains":
            return b not in a
        case "regex":
            try:
                return re.search(right, left, 0 if case_sensitive else re.IGNORECASE) is not None
            except re.error as exc:
                raise RunFailure("CONDITION_INVALID", f"invalid regular expression: {exc}") from exc
        case "is_empty":
            return not left.strip()
        case "not_empty":
            return bool(left.strip())
        case "greater_than" | "less_than":
            x, y = _number(left), _number(right)
            if x is None or y is None:
                raise RunFailure("CONDITION_INVALID", f"'{op}' needs numbers, got '{left[:50]}' and '{right[:50]}'")
            return x > y if op == "greater_than" else x < y
    raise RunFailure("CONDITION_INVALID", f"unknown operator '{op}'")


class WorkflowExecutor:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.events = RunEventRepository(db)
        self.agents = AgentRepository(db)
        self.versions = AgentVersionRepository(db)
        self.tools = ToolRepository(db)
        self.agent_executor = AgentExecutor(db)

    async def _agent(self, run: dict, step: dict, ctx: dict) -> tuple[dict, dict, bool]:
        ws = run["workspace_id"]
        a = await self.agents.get(ws, step["agent_id"])
        if not a or a["status"] != "published" or not a.get("published_version"):
            raise RunFailure("AGENT_NOT_RUNNABLE", f"agent {step['agent_id']} is missing or not published")
        v = await self.versions.by_number(ws, a["_id"], a["published_version"])
        if not v:
            raise RunFailure("VERSION_MISSING", f"published version of agent '{a['name']}' is missing")
        message = render(step.get("message") or "{{ input.message }}", ctx)
        if not message.strip():
            raise RunFailure("INVALID_INPUT", f"step '{step['id']}' rendered an empty message")
        sub_input = {"message": message, "variables": run["input"].get("variables", {})}
        if run["input"].get("memory_scope"):
            sub_input["memory_scope"] = run["input"]["memory_scope"]
        sub = {"_id": run["_id"], "workspace_id": ws, "agent_id": a["_id"], "attempt": run.get("attempt", 1),
               "created_by": run.get("created_by", "system"), "config": v["config"], "input": sub_input}
        res: ExecutionResult = await self.agent_executor.execute(sub)
        out = {"text": res.output.get("text", ""), "agent_id": a["_id"], "agent_name": a["name"],
               "agent_version": v["version"], "model": res.output.get("model"),
               "provider_kind": res.output.get("provider_kind")}
        if "structured" in res.output:
            out["structured"] = res.output["structured"]
        if "citations" in res.output:
            out["citations"] = res.output["citations"]
        return out, res.usage, res.demo

    async def _tool(self, run: dict, step: dict, ctx: dict) -> dict:
        found = await self.tools.many(run["workspace_id"], [step["tool_id"]])
        if not found:
            raise RunFailure("TOOL_NOT_FOUND", f"tool {step['tool_id']} not found")
        t = found[0]
        args = render_value(step.get("arguments") or {}, ctx)
        await self.events.append(run["_id"], run["workspace_id"], "tool.call",
                                 {"tool": t["name"], "call_id": step["id"], "arguments": args})
        started = time.monotonic()
        try:
            content = redact_text(await execute_tool(t, args))
        except ToolExecutionError as exc:
            await self.events.append(run["_id"], run["workspace_id"], "tool.result", {
                "tool": t["name"], "call_id": step["id"], "ok": False,
                "latency_ms": int((time.monotonic() - started) * 1000), "bytes": 0, "preview": str(exc)[:500]})
            raise RunFailure("TOOL_FAILED", redact_text(f"tool '{t['name']}' failed: {exc}")) from exc
        await self.events.append(run["_id"], run["workspace_id"], "tool.result", {
            "tool": t["name"], "call_id": step["id"], "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000), "bytes": len(content), "preview": content[:500]})
        out: dict = {"text": content, "tool": t["name"]}
        try:
            out["json"] = json.loads(content)
        except ValueError:
            pass
        return out

    async def _knowledge(self, run: dict, step: dict, ctx: dict) -> dict:
        query = render(step.get("query") or "{{ input.message }}", ctx)
        try:
            hits = await KnowledgeService(self.db).search(run["workspace_id"], list(step["knowledge_base_ids"]),
                                                          query, int(step.get("top_k") or 5))
        except ProviderError as exc:
            raise RunFailure("KNOWLEDGE_UNAVAILABLE", redact_text(f"knowledge search failed: {exc.message}")) from exc
        await self.events.append(run["_id"], run["workspace_id"], "knowledge.retrieved", {
            "count": len(hits), "sources": [{"n": i + 1, "title": h["title"], "doc_id": h["doc_id"],
                                             "score": h["score"]} for i, h in enumerate(hits)]})
        text = "\n\n".join(f"[{i + 1}] {h['title']}\n{h['text']}" for i, h in enumerate(hits))
        return {"text": text, "count": len(hits),
                "hits": [{"title": h["title"], "doc_id": h["doc_id"], "kb_id": h["kb_id"], "score": h["score"],
                          "excerpt": h["text"][:300]} for h in hits]}

    async def execute(self, run: dict) -> ExecutionResult:
        ws, run_id = run["workspace_id"], run["_id"]
        definition = run["config"]
        steps: list[dict] = definition.get("steps") or []
        if not steps:
            raise RunFailure("WORKFLOW_EMPTY", "the workflow has no steps")
        index = {s["id"]: i for i, s in enumerate(steps)}
        limit = int(definition.get("max_step_executions") or 50)
        totals = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        demo = False
        ctx: dict = {"input": {"message": run["input"].get("message", ""),
                               "variables": run["input"].get("variables") or {}},
                     "steps": {}, "last": {"text": ""}}
        path: list[str] = []
        i: int | None = 0
        while i is not None and i < len(steps):
            step = steps[i]
            if len(path) >= limit:
                raise RunFailure("STEP_LIMIT", f"stopped after {limit} step executions (loop guard)")
            path.append(step["id"])
            await self.events.append(run_id, ws, "workflow.step.started",
                                     {"step": step["id"], "type": step["type"], "name": step.get("name") or "",
                                      "n": len(path)})
            started = time.monotonic()
            route: str | None = step.get("next")
            try:
                if step["type"] == "agent":
                    out, usage, used_demo = await self._agent(run, step, ctx)
                    demo = demo or used_demo
                    totals["input_tokens"] += usage["input_tokens"]
                    totals["output_tokens"] += usage["output_tokens"]
                    totals["cost_usd"] = round(totals["cost_usd"] + usage["cost_usd"], 8)
                elif step["type"] == "tool":
                    out = await self._tool(run, step, ctx)
                elif step["type"] == "knowledge":
                    out = await self._knowledge(run, step, ctx)
                elif step["type"] == "transform":
                    out = {"text": render(step["template"], ctx)}
                else:  # condition
                    c = step["condition"]
                    left, right = render(c.get("left", ""), ctx), render(c.get("right", ""), ctx)
                    result = evaluate(c["op"], left, right, bool(c.get("case_sensitive")))
                    route = step.get("on_true") if result else step.get("on_false")
                    # A condition passes the previous text through, so later steps can keep using {{ last.text }}.
                    out = {"text": ctx["last"]["text"], "result": result, "left": left[:500], "right": right[:500]}
            except TemplateError as exc:
                await self.events.append(run_id, ws, "workflow.step.failed", {"step": step["id"], "error": str(exc)})
                raise RunFailure("TEMPLATE_ERROR", f"step '{step['id']}': {exc}") from exc
            except RunFailure as f:
                await self.events.append(run_id, ws, "workflow.step.failed",
                                         {"step": step["id"], "code": f.code, "error": f.message})
                raise RunFailure(f.code, f"step '{step['id']}': {f.message}") from f
            out["duration_ms"] = int((time.monotonic() - started) * 1000)
            ctx["steps"][step["id"]] = out
            ctx["last"] = out
            nxt = END if route == END else (index[route] if route else i + 1)
            await self.events.append(run_id, ws, "workflow.step.completed", {
                "step": step["id"], "type": step["type"], "duration_ms": out["duration_ms"],
                "preview": str(out.get("text", ""))[:300],
                **({"result": out["result"]} if "result" in out else {}),
                "next": END if nxt == END or nxt >= len(steps) else steps[nxt]["id"]})
            i = None if nxt == END else nxt

        final = ctx["last"]
        output = {"text": final.get("text", ""), "path": path, "steps": ctx["steps"], "workflow": True}
        if "structured" in final:
            output["structured"] = final["structured"]
        return ExecutionResult(output=output, usage=totals, demo=demo)
