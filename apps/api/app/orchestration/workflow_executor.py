"""Executes a workflow run step by step inside the worker.

- Steps run in list order unless routed with ``next`` / ``on_true`` / ``on_false`` (or "end").
- Agent steps run the agent's *published* version through the regular AgentExecutor, with the
  workflow run as the parent: its model calls, tool calls, usage records and budget checks are
  exactly those of a normal agent run, and its events land in this run's timeline.
- Every step emits ``workflow.step.started`` and ``workflow.step.completed`` (or ``.failed``).
- ``max_step_executions`` bounds loops built with routing, so a cycle cannot run forever.
- Supervisor steps lead teams (see ``app.orchestration.team``): each round the supervisor agent
  delegates tasks, the team members run in parallel (bounded by ``parallelism``), and their results
  go back to the supervisor. Team members that are supervisors lead their own sub-teams. Every
  delegated task counts against ``max_delegations``. Team members never run in the main flow.
- Cancellation and timeouts are applied by the worker supervisor cancelling this coroutine.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field

from pymongo.asynchronous.database import AsyncDatabase

from app.core.logging import redact_text
from app.orchestration import team
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


@dataclass
class RunState:
    """Per-run accounting. The executor instance is shared by concurrent runs, so state lives here."""
    max_delegations: int = 200
    totals: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
    demo: bool = False
    delegations: int = 0

    def account(self, usage: dict, demo: bool) -> None:
        t = self.totals
        t["input_tokens"] += usage["input_tokens"]
        t["output_tokens"] += usage["output_tokens"]
        t["cost_usd"] = round(t["cost_usd"] + usage["cost_usd"], 8)
        self.demo = self.demo or demo


class WorkflowExecutor:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.events = RunEventRepository(db)
        self.agents = AgentRepository(db)
        self.versions = AgentVersionRepository(db)
        self.tools = ToolRepository(db)
        self.agent_executor = AgentExecutor(db)

    async def _load_agent(self, ws: str, agent_id: str) -> tuple[dict, dict]:
        a = await self.agents.get(ws, agent_id)
        if not a or a["status"] != "published" or not a.get("published_version"):
            raise RunFailure("AGENT_NOT_RUNNABLE", f"agent {agent_id} is missing or not published")
        v = await self.versions.by_number(ws, a["_id"], a["published_version"])
        if not v:
            raise RunFailure("VERSION_MISSING", f"published version of agent '{a['name']}' is missing")
        return a, v

    async def _run_agent(self, run: dict, a: dict, v: dict, message: str) -> tuple[dict, dict, bool]:
        ws = run["workspace_id"]
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

    async def _agent(self, run: dict, step: dict, ctx: dict) -> tuple[dict, dict, bool]:
        a, v = await self._load_agent(run["workspace_id"], step["agent_id"])
        message = render(step.get("message") or "{{ input.message }}", ctx)
        if not message.strip():
            raise RunFailure("INVALID_INPUT", f"step '{step['id']}' rendered an empty message")
        return await self._run_agent(run, a, v, message)

    async def _supervise(self, run: dict, step: dict, brief: str, ctx: dict, by_id: dict[str, dict],
                         st: RunState, depth: int = 0) -> dict:
        """Plan → delegate (parallel) → review loop of one supervisor step. Returns the step output."""
        ws, run_id = run["workspace_id"], run["_id"]
        lead, lead_v = await self._load_agent(ws, step["agent_id"])
        lead_name = step.get("name") or lead["name"]
        members: list[team.Member] = []
        loaded: dict[str, tuple[dict, dict]] = {}
        for mid in step.get("delegates") or []:
            m = by_id[mid]
            a, v = await self._load_agent(ws, m["agent_id"])
            loaded[mid] = (a, v)
            members.append(team.Member(id=mid, name=m.get("name") or a["name"],
                                       role=m.get("role") or a.get("description") or "",
                                       leads_team=m["type"] == "supervisor"))
        max_rounds = int(step.get("max_rounds") or 3)
        sem = asyncio.Semaphore(int(step.get("parallelism") or 8))
        reports: list[team.Report] = []
        final: str | None = None
        rounds = 0
        await self.events.append(run_id, ws, "team.started", {
            "step": step["id"], "lead": lead_name, "depth": depth,
            "members": [{"id": m.id, "name": m.name, "leads_team": m.leads_team} for m in members]})

        async def work(r: int, t: team.Task) -> team.Report:
            member = team.resolve_member(t.to, members)
            if member is None:
                return team.Report(r, t.to, t.task, False, f"there is no team member '{t.to}'; "
                                   f"use one of: {', '.join(m.id for m in members)}")
            async with sem:
                await self.events.append(run_id, ws, "team.task.started", {
                    "step": step["id"], "member": member.id, "name": member.name, "round": r,
                    "task": t.task[:500]})
                started = time.monotonic()
                try:
                    if member.leads_team:
                        out = await self._supervise(run, by_id[member.id], t.task, ctx, by_id, st, depth + 1)
                    else:
                        a, v = loaded[member.id]
                        out, usage, used_demo = await self._run_agent(
                            run, a, v, team.member_message(brief, t.task, member, lead_name))
                        st.account(usage, used_demo)
                except RunFailure as f:
                    if f.code in ("BUDGET_EXCEEDED", "DELEGATION_LIMIT"):
                        raise
                    await self.events.append(run_id, ws, "team.task.failed", {
                        "step": step["id"], "member": member.id, "round": r, "code": f.code, "error": f.message})
                    return team.Report(r, member.id, t.task, False, f"{f.code}: {f.message}")
                out["duration_ms"] = int((time.monotonic() - started) * 1000)
                ctx["steps"][member.id] = out
                await self.events.append(run_id, ws, "team.task.completed", {
                    "step": step["id"], "member": member.id, "round": r, "duration_ms": out["duration_ms"],
                    "preview": str(out.get("text", ""))[:300]})
                return team.Report(r, member.id, t.task, True, str(out.get("text", "")))

        while final is None:
            rounds += 1
            force = rounds > max_rounds
            msg = team.supervisor_message(brief, members, reports, min(rounds, max_rounds), max_rounds, force)
            out, usage, used_demo = await self._run_agent(run, lead, lead_v, msg)
            st.account(usage, used_demo)
            decision = team.parse_decision(out.get("text", ""), {m.id for m in members})
            if decision.final is not None or force:
                final = decision.final if decision.final is not None else (
                    team.fallback_final(reports) or out.get("text", ""))
                break
            if st.delegations + len(decision.tasks) > st.max_delegations:
                raise RunFailure("DELEGATION_LIMIT", f"supervisors delegated more than {st.max_delegations} "
                                                     "tasks in this run (max_delegations)")
            st.delegations += len(decision.tasks)
            await self.events.append(run_id, ws, "team.plan", {
                "step": step["id"], "round": rounds, "thoughts": decision.thoughts[:1000],
                "tasks": [{"to": t.to, "task": t.task[:300]} for t in decision.tasks]})
            reports += await asyncio.gather(*(work(rounds, t) for t in decision.tasks))

        await self.events.append(run_id, ws, "team.completed", {
            "step": step["id"], "rounds": rounds, "tasks": len(reports),
            "failed": sum(1 for r in reports if not r.ok), "preview": final[:300]})
        return {"text": final, "agent_id": lead["_id"], "agent_name": lead["name"], "rounds": rounds,
                "tasks": [{"round": r.round, "to": r.to, "ok": r.ok, "task": r.task[:300]} for r in reports]}

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
        by_id = {s["id"]: s for s in steps}
        members = {d for s in steps for d in (s.get("delegates") or [])}
        limit = int(definition.get("max_step_executions") or 50)
        st = RunState(max_delegations=int(definition.get("max_delegations") or 200))

        def following(j: int) -> int:
            """The next step in list order that runs in the main flow (team members are skipped)."""
            while j < len(steps) and steps[j]["id"] in members:
                j += 1
            return j

        ctx: dict = {"input": {"message": run["input"].get("message", ""),
                               "variables": run["input"].get("variables") or {}},
                     "steps": {}, "last": {"text": ""}}
        path: list[str] = []
        i: int | None = following(0)
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
                    st.account(usage, used_demo)
                elif step["type"] == "supervisor":
                    brief = render(step.get("message") or "{{ input.message }}", ctx)
                    if not brief.strip():
                        raise RunFailure("INVALID_INPUT", f"step '{step['id']}' rendered an empty brief")
                    out = await self._supervise(run, step, brief, ctx, by_id, st)
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
            nxt = END if route == END else (index[route] if route else following(i + 1))
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
        return ExecutionResult(output=output, usage=st.totals, demo=st.demo)
