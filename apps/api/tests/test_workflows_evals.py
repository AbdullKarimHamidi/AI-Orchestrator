"""Workflows, evaluations, memory and billing: pure logic plus end-to-end runs through the worker."""
import pytest
from pydantic import ValidationError

from app.orchestration.templating import TemplateError, render, render_value
from app.orchestration.workflow_executor import evaluate
from app.repositories.base import now
from app.schemas.workflows import WorkflowDefinition
from app.services.evaluations import score
from tests.conftest import published_agent
from tests.test_runs import claim_and_process, drain

CTX = {"input": {"message": "hi", "variables": {"n": 3, "obj": {"a": 1}}}, "steps": {"s1": {"text": "out"}},
       "last": {"text": "out"}}


def test_templates_are_strict_and_typed():
    assert render("{{ input.message }} / {{steps.s1.text}}", CTX) == "hi / out"
    assert render("n={{ input.variables.n }}", CTX) == "n=3"
    assert render_value({"x": "{{ input.variables.obj }}", "y": ["{{ input.variables.n }}"]}, CTX) == \
        {"x": {"a": 1}, "y": [3]}
    with pytest.raises(TemplateError):
        render("{{ steps.missing.text }}", CTX)
    # no expressions: anything that is not a dotted path is left as literal text
    assert render("{{ 1 + 1 }}", CTX) == "{{ 1 + 1 }}"


def test_condition_operators():
    assert evaluate("contains", "Refund please", "refund")
    assert not evaluate("contains", "Refund please", "refund", case_sensitive=True)
    assert evaluate("regex", "order #123", r"#\d+")
    assert evaluate("greater_than", "10", "9.5") and evaluate("is_empty", "  ", "")


def test_definition_graph_validation():
    ok = {"steps": [{"id": "a", "type": "transform", "template": "x", "next": "end"}]}
    assert WorkflowDefinition.model_validate(ok).steps[0].next == "end"
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({"steps": [{"id": "a", "type": "transform", "template": "x", "next": "b"}]})
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({"steps": [{"id": "a", "type": "agent"}]})
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({"steps": [{"id": "a", "type": "transform", "template": "x"}] * 2})


def test_scorers():
    assert score({"type": "contains"}, "The answer is 42", "42") == (True, "expected text found in output")
    assert score({"type": "exact", "case_sensitive": True}, "Yes", "yes")[0] is False
    assert score({"type": "json_valid"}, 'Sure: {"a": 1}', "")[0] is True
    assert score({"type": "regex"}, "ID-77", r"id-\d+")[0] is True


async def test_workflow_routes_and_runs_agent(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    definition = {"steps": [
        {"id": "classify", "type": "condition",
         "condition": {"left": "{{ input.message }}", "op": "contains", "right": "refund"},
         "on_true": "answer", "on_false": "polite"},
        {"id": "polite", "type": "transform", "template": "No refund requested: {{ input.message }}", "next": "end"},
        {"id": "answer", "type": "agent", "agent_id": agent["id"], "message": "Handle: {{ input.message }}"},
        {"id": "wrap", "type": "transform", "template": "Agent said: {{ steps.answer.text }}"},
    ]}
    r = await alice.post("/workflows", json={"name": "Support triage", "definition": definition})
    assert r.status_code == 201, r.text
    wf = r.json()
    assert (await alice.post(f"/workflows/{wf['id']}/runs", json={"input": {"message": "x"}})).status_code == 409
    assert (await alice.post(f"/workflows/{wf['id']}/publish", json={"note": "v1"})).status_code == 200

    rid = (await alice.post(f"/workflows/{wf['id']}/runs", json={"input": {"message": "I want a refund"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await alice.get(f"/runs/{rid}")).json()
    assert run["kind"] == "workflow" and run["workflow_id"] == wf["id"] and run["demo"] is True
    assert run["output"]["path"] == ["classify", "answer", "wrap"]
    assert run["output"]["text"].startswith("Agent said: [DEMO]") and run["usage"]["input_tokens"] > 0
    types = [e["type"] for e in (await alice.get(f"/runs/{rid}/events")).json()]
    assert types.count("workflow.step.completed") == 3 and "model.response" in types

    rid = (await alice.post(f"/workflows/{wf['id']}/runs", json={"input": {"message": "hello"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await alice.get(f"/runs/{rid}")).json()
    assert run["output"]["path"] == ["classify", "polite"] and run["output"]["text"] == "No refund requested: hello"
    listed = (await alice.get(f"/workflows/{wf['id']}/runs")).json()
    assert listed["total"] == 2


async def test_workflow_loop_guard(alice, database):
    await drain(database)
    definition = {"max_step_executions": 5,
                  "steps": [{"id": "spin", "type": "transform", "template": "again", "next": "spin"}]}
    wf = (await alice.post("/workflows", json={"name": "Loop", "definition": definition})).json()
    rid = (await alice.post(f"/workflows/{wf['id']}/runs",
                            json={"input": {"message": "go"}, "source": "draft"})).json()["id"]
    assert await claim_and_process(database, rid) == "failed"
    assert (await alice.get(f"/runs/{rid}")).json()["error"]["code"] == "STEP_LIMIT"


async def test_evaluation_scores_and_compares(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    ds = (await alice.post("/eval-datasets", json={"name": "echo", "cases": [
        {"input": "alpha", "expected": "alpha"}, {"input": "beta", "expected": "gamma"}]})).json()
    assert ds["case_count"] == 2 and [c["id"] for c in ds["cases"]] == ["case_1", "case_2"]
    ev = (await alice.post("/eval-runs", json={"dataset_id": ds["id"], "agent_id": agent["id"]})).json()
    assert ev["status"] == "running" and ev["summary"]["finished"] == 0
    for item in ev["results"]:
        assert await claim_and_process(database, item["run_id"]) == "completed"
    done = (await alice.get(f"/eval-runs/{ev['id']}")).json()
    assert done["status"] == "completed" and done["summary"]["passed"] == 1 and done["summary"]["pass_rate"] == 0.5
    ev2 = (await alice.post("/eval-runs", json={"dataset_id": ds["id"], "agent_id": agent["id"],
                                                "scorer": {"type": "not_empty"}})).json()
    for item in ev2["results"]:
        await claim_and_process(database, item["run_id"])
    cmp = (await alice.get("/eval-runs/compare", params={"a": ev["id"], "b": ev2["id"]})).json()
    assert cmp["fixed"] == 1 and cmp["regressed"] == 0


async def test_memory_is_added_to_prompt_and_forgotten(alice, database):
    await drain(database)
    agent = await published_agent(alice, memory={"enabled": True, "top_k": 5, "save_conversations": True})
    r = await alice.post("/memories", json={"agent_id": agent["id"], "scope": "user-1", "content": "Prefers email"})
    assert r.status_code == 201, r.text
    rid = (await alice.post("/runs", json={"agent_id": agent["id"],
                                           "input": {"message": "hi", "memory_scope": "user-1"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    ev = {e["type"]: e["data"] for e in (await alice.get(f"/runs/{rid}/events")).json()}
    assert ev["memory.loaded"]["count"] == 1 and "memory.saved" in ev
    scopes = (await alice.get("/memories/scopes", params={"agent_id": agent["id"]})).json()
    assert scopes[0]["scope"] == "user-1" and scopes[0]["count"] == 2
    r = await alice.post("/memories/forget", json={"agent_id": agent["id"], "scope": "user-1"})
    assert r.json() == {"deleted": 2}


async def test_plan_quota_and_statements(alice, database):
    over = await alice.get("/billing")
    assert over.status_code == 200 and over.json()["plan"]["id"] == "self_hosted"
    assert (await alice.post("/billing/plan", json={"plan": "starter"})).json()["plan"]["runs_per_month"] == 1000
    await database["runs"].insert_many([{"_id": f"run_q{i}_{alice.workspace_id}", "workspace_id": alice.workspace_id,
                                         "status": "completed", "created_at": now()} for i in range(1000)])
    agent = await published_agent(alice)
    r = await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RUN_QUOTA_EXCEEDED"
    st = (await alice.get("/billing/statements", params={"months": 3})).json()
    assert len(st) == 3 and st[0]["current"] and st[0]["runs"] >= 1000
