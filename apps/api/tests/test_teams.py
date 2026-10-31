"""Hierarchical teams (supervisor steps) and the Ollama adapter. These tests need no database:
the executor runs against in-memory fakes, the adapter against httpx.MockTransport."""
import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.orchestration import team
from app.orchestration.agent_executor import RunFailure
from app.orchestration.workflow_executor import WorkflowExecutor
from app.providers.base import ChatMessage, ChatRequest, ProviderConfig, ProviderError
from app.providers.ollama import OllamaAdapter, normalize_ollama_url
from app.schemas.workflows import WorkflowDefinition


def step(id_, type_="agent", **kw):
    base = {"id": id_, "type": type_, "agent_id": f"agt_{id_}"}
    return base | kw


# ---------- schema ----------

def test_supervisor_definition_is_valid_and_members_leave_the_main_flow():
    d = WorkflowDefinition.model_validate({"steps": [
        step("lead", "supervisor", delegates=["dev", "qa"]),
        step("dev", role="writes code"), step("qa", role="tests code"),
        {"id": "wrap", "type": "transform", "template": "{{ last.text }}"},
    ]})
    assert d.team_members() == {"dev", "qa"}


@pytest.mark.parametrize("steps, message", [
    ([step("lead", "supervisor", delegates=[])], "at least one team member"),
    ([step("lead", "supervisor", delegates=["lead"])], "itself"),
    ([step("lead", "supervisor", delegates=["ghost"])], "not a step"),
    ([step("lead", "supervisor", delegates=["t"]), {"id": "t", "type": "transform", "template": "x"}],
     "must be an agent or supervisor"),
    ([step("a", "supervisor", delegates=["w"]), step("b", "supervisor", delegates=["w"]), step("w")],
     "reports to both"),
    ([step("a", "supervisor", delegates=["b"]), step("b", "supervisor", delegates=["a"])], "loop"),
    ([step("lead", "supervisor", delegates=["w"], next="w"), step("w")], "only runs when its supervisor"),
    ([step("w", delegates=["x"]), step("x")], "only supervisor steps"),
])
def test_invalid_teams_are_rejected(steps, message):
    with pytest.raises(ValidationError, match=message):
        WorkflowDefinition.model_validate({"steps": steps})


# ---------- protocol ----------

def test_parse_decision_reads_tasks_final_and_free_text():
    members = {"dev", "qa"}
    d = team.parse_decision('```json\n{"thoughts": "split", "tasks": [{"to": "dev", "task": "build"}, '
                            '{"to": "qa", "task": " "}]}\n```', members)
    assert [(t.to, t.task) for t in d.tasks] == [("dev", "build")] and d.final is None
    d = team.parse_decision('Sure! {"final": "all done"}', members)
    assert d.final == "all done" and not d.tasks
    d = team.parse_decision("I just wrote the answer myself.", members)
    assert d.final == "I just wrote the answer myself." and not d.raw_was_json


def test_resolve_member_accepts_display_names():
    ms = [team.Member("frontend_dev", "Frontend Developer", "")]
    assert team.resolve_member("Frontend Developer", ms) is ms[0]
    assert team.resolve_member("FRONTEND_DEV", ms) is ms[0]
    assert team.resolve_member("nobody", ms) is None


def test_supervisor_message_lists_roster_and_results():
    ms = [team.Member("dev", "Dev", "writes code"), team.Member("sub", "Sub lead", "", leads_team=True)]
    msg = team.supervisor_message("Build a todo app", ms, [team.Report(1, "dev", "build", True, "code here")], 2, 2)
    assert '"dev" (Dev): writes code' in msg and "leads a sub-team" in msg
    assert "Build a todo app" in msg and 'member="dev" status="done"' in msg and "last round" in msg


# ---------- executor with fakes ----------

class FakeEvents:
    def __init__(self):
        self.items: list[tuple[str, dict]] = []

    async def append(self, run_id, ws, type_, data):
        self.items.append((type_, data))
        return len(self.items)


def make_executor(script):
    """``script(agent_id, message) -> text``; every agent call costs 1 token in and out."""
    ex = WorkflowExecutor.__new__(WorkflowExecutor)
    ex.events = FakeEvents()
    calls: list[tuple[str, str]] = []
    running = {"now": 0, "peak": 0}

    async def load(ws, agent_id):
        return {"_id": agent_id, "name": agent_id.removeprefix("agt_").title(), "description": ""}, \
            {"version": 1, "config": {}}

    async def run_agent(run, a, v, message):
        calls.append((a["_id"], message))
        running["now"] += 1
        running["peak"] = max(running["peak"], running["now"])
        await asyncio.sleep(0.01)
        running["now"] -= 1
        return ({"text": script(a["_id"], message), "agent_id": a["_id"]},
                {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0}, False)

    ex._load_agent = load
    ex._run_agent = run_agent
    return ex, calls, running


def run_doc(steps, **definition):
    return {"_id": "run_1", "workspace_id": "ws_1", "input": {"message": "Build a shop"},
            "config": {"steps": steps, "max_step_executions": 50, **definition}}


async def test_supervisor_delegates_in_parallel_reviews_and_finishes():
    workers = [f"w{i}" for i in range(12)]

    def script(agent_id, message):
        if agent_id == "agt_lead":
            if "Results from your team" not in message:
                return json.dumps({"thoughts": "fan out", "tasks": [{"to": w, "task": f"part {w}"} for w in workers]})
            return json.dumps({"final": "merged: " + ",".join(sorted(w for w in workers if f'member="{w}"' in message))})
        return f"work of {agent_id}"

    ex, calls, running = make_executor(script)
    steps = [step("lead", "supervisor", delegates=workers, parallelism=4),
             *[step(w, role=f"role {w}") for w in workers],
             {"id": "after", "type": "transform", "template": "final={{ last.text }} w3={{ steps.w3.text }}"}]
    res = await ex.execute(run_doc(steps))
    assert res.output["path"] == ["lead", "after"]  # members never run in the main flow
    assert res.output["text"] == "final=merged: " + ",".join(sorted(workers)) + " w3=work of agt_w3"
    assert len(calls) == 14 and res.usage["input_tokens"] == 14
    assert 1 < running["peak"] <= 4  # parallel, bounded by parallelism
    assert "role w5" in next(m for a, m in calls if a == "agt_w5")
    types = [t for t, _ in ex.events.items]
    assert types.count("team.task.completed") == 12 and "team.completed" in types


async def test_nested_supervisors_and_unknown_member_feedback():
    def script(agent_id, message):
        if agent_id == "agt_ceo":
            if "Results from your team" not in message:
                return json.dumps({"tasks": [{"to": "eng", "task": "build backend"}, {"to": "ghost", "task": "x"}]})
            assert 'member="ghost" status="FAILED"' in message
            return json.dumps({"final": "ceo done"})
        if agent_id == "agt_eng":
            if "Results from your team" not in message:
                assert "build backend" in message
                return json.dumps({"tasks": [{"to": "api", "task": "write api"}]})
            return json.dumps({"final": "eng done"})
        return "api code"

    ex, calls, _ = make_executor(script)
    steps = [step("ceo", "supervisor", delegates=["eng"]), step("eng", "supervisor", delegates=["api"]),
             step("api")]
    res = await ex.execute(run_doc(steps))
    assert res.output["text"] == "ceo done"
    assert res.output["steps"]["eng"]["text"] == "eng done"
    assert [a for a, _ in calls] == ["agt_ceo", "agt_eng", "agt_api", "agt_eng", "agt_ceo"]


async def test_round_limit_forces_a_final_answer_and_delegation_cap_holds():
    def keeps_delegating(agent_id, message):
        if agent_id == "agt_lead":
            return json.dumps({"tasks": [{"to": "w", "task": "again"}]})
        return "partial work"

    ex, calls, _ = make_executor(keeps_delegating)
    res = await ex.execute(run_doc([step("lead", "supervisor", delegates=["w"], max_rounds=2), step("w")]))
    assert res.output["text"] == "## w\npartial work"  # forced finish falls back to the team's work
    assert [a for a, _ in calls] == ["agt_lead", "agt_w", "agt_lead", "agt_w", "agt_lead"]

    ex, _, _ = make_executor(keeps_delegating)
    with pytest.raises(RunFailure) as e:
        await ex.execute(run_doc([step("lead", "supervisor", delegates=["w"], max_rounds=5), step("w")],
                                 max_delegations=3))
    assert e.value.code == "DELEGATION_LIMIT"


# ---------- Ollama adapter ----------

def test_normalize_ollama_url():
    assert normalize_ollama_url("http://localhost:11434/v1/") == "http://localhost:11434"
    assert normalize_ollama_url("http://10.0.0.5:11434/api") == "http://10.0.0.5:11434"
    assert normalize_ollama_url("http://box:11434") == "http://box:11434"


def adapter(handler, url="http://localhost:11434"):
    return OllamaAdapter(ProviderConfig("ollama", None, url, 10), transport=httpx.MockTransport(handler))


async def test_ollama_chat_uses_openai_endpoint_and_lists_pulled_models():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:latest"}, {"name": "llama3.2:latest"}]})
        body = json.loads(request.content)
        assert body["model"] == "llama3.2" and "Authorization" not in request.headers
        return httpx.Response(200, json={"id": "c1", "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    a = adapter(handler, "http://localhost:11434/v1")
    assert await a.list_models() == ["llama3.2:latest", "qwen2.5:latest"]
    r = await a.chat(ChatRequest(model="llama3.2", messages=[ChatMessage("user", "hello")]))
    assert r.text == "hi" and seen == [("GET", "/api/tags"), ("POST", "/v1/chat/completions")]


async def test_ollama_errors_explain_what_to_do():
    def down(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="cannot reach Ollama at http://localhost:11434"):
        await adapter(down).list_models()

    def missing(request):
        return httpx.Response(404, json={"error": {"message": "model 'phi4' not found"}})

    with pytest.raises(ProviderError, match="ollama pull phi4"):
        await adapter(missing).chat(ChatRequest(model="phi4", messages=[ChatMessage("user", "x")]))
