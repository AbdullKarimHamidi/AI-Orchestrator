"""Project build: team definition, file extraction, and a full build round on a mocked provider."""
import json
import re

import httpx

from app.orchestration import project_build as pb
from app.providers import registry
from app.schemas.workflows import WorkflowDefinition
from app.workers.main import Worker


def test_extract_files_reads_file_blocks_and_rejects_unsafe_paths():
    text = ("Here you go\n```file:web/index.html\n<h1>Hi</h1>\n```\n"
            "```css path=web/style.css\nh1{color:red}\n```\n"
            "```file:../etc/passwd\nnope\n```\n```python\nprint('not a file')\n```\n"
            "```file:web/index.html\n<h1>Hi v2</h1>\n```")
    files = pb.extract_files(text)
    assert files == {"web/index.html": "<h1>Hi v2</h1>\n", "web/style.css": "h1{color:red}\n"}


def test_build_definition_makes_a_valid_team_tree():
    project = {"name": "P", "idea": "x", "director_agent_id": "agt_dir", "reviewer_agent_ids": ["agt_rev"],
               "planning_model": {"provider_id": "prv_or", "model": "m:free", "provider_name": "OR"},
               "teams": [{"name": "UI", "kind": "ui", "responsibility": "pages", "agent_ids": ["agt_ui"]},
                         {"name": "Backend", "kind": "backend", "responsibility": "API", "agent_ids": ["agt_b1", "agt_b2"],
                          "lead_agent_id": "agt_lead", "parallelism": 3},
                         {"name": "Database", "kind": "database", "responsibility": "schema", "agent_ids": []}]}
    d = pb.build_definition(project, {"agt_b1": "Coder", "agt_b2": "Coder"})
    WorkflowDefinition.model_validate(d)
    by_id = {s["id"]: s for s in d["steps"]}
    director = by_id["director"]
    assert director["type"] == "supervisor" and director["next"] == "plan_check"
    assert director["delegates"] == ["ui", "backend_coordinator", "plan_reviewer_1"]
    assert by_id["backend_coordinator"]["agent_id"] == "agt_lead"
    assert by_id["backend_coordinator"]["delegates"] == ["backend_1", "backend_2"]
    assert all(s["model"] == {"provider_id": "prv_or", "model": "m:free"} for s in d["steps"])
    assert pb.file_steps(d) == ["director", "backend_coordinator", "ui", "backend_1", "backend_2"]


def _team_handler(calls: list[str]):
    """Plays every role: the director and coordinators delegate to everyone once, members write files."""
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        msg = body["messages"][-1]["content"]
        calls.append(msg[:40])
        if "Team members (use the id exactly" in msg:
            if "Results from your team so far" in msg:
                text = json.dumps({"thoughts": "done", "final": "All teams delivered. See their files."})
            else:
                ids = re.findall(r'^- "([a-z0-9_]+)"', msg, re.M)
                text = json.dumps({"thoughts": "split", "tasks": [{"to": i, "task": f"do part {i}"} for i in ids]})
        elif msg.startswith("Check the delivered project"):
            text = "Everything in the plan is there.\nVERDICT: COMPLETE"
        elif "Plan compliance reviewer" in msg:
            text = "Looks right. VERDICT: COMPLETE"
        elif "UI / frontend team" in msg:
            text = "```file:web/index.html\n<!doctype html><h1>Habit tracker</h1>\n```\nBuilt the page."
        elif "Backend team" in msg:
            text = "```file:backend/app.py\nprint('api')\n```"
        else:
            text = "ok"
        return httpx.Response(200, json={"id": "x", "model": body["model"], "choices": [{
            "index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5}})
    return handler


async def _agent(api, provider_id: str, name: str) -> str:
    a = (await api.post("/agents", json={"name": name, "config": {
        "system_prompt": "Work well.", "model": {"provider_id": provider_id, "model": "m:free"}}})).json()
    assert (await api.post(f"/agents/{a['id']}/publish", json={"note": "v1"})).status_code == 200
    return a["id"]


async def test_full_build_round_writes_files_and_reviews(alice, database):
    await database["runs"].update_many({"status": "queued"}, {"$set": {"status": "cancelled"}})
    orp = (await alice.post("/model-providers/presets/openrouter", json={"api_key": "sk-or-test"})).json()
    director, ui, b1, b2, lead, reviewer = [await _agent(alice, orp["id"], n) for n in
                                            ("Director", "UI dev", "API dev 1", "API dev 2", "Backend lead", "QA")]
    project = (await alice.post("/projects", json={
        "name": "Built project", "idea": "Build a habit tracker with a web page and an API",
        "planning_agent_ids": [director],
        "planning_model": {"provider_id": orp["id"], "model": "meta-llama/llama-3.3-70b-instruct:free"}})).json()
    r = await alice.patch(f"/projects/{project['id']}", json={
        "revision": project["revision"], "director_agent_id": director, "reviewer_agent_ids": [reviewer],
        "teams": [{"id": "ui", "name": "UI", "kind": "ui", "responsibility": "Pages", "agent_ids": [ui]},
                  {"id": "be", "name": "Backend", "kind": "backend", "responsibility": "API",
                   "agent_ids": [b1, b2], "lead_agent_id": lead}]})
    assert r.status_code == 200, r.text

    started = await alice.post(f"/projects/{project['id']}/build", json={})
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    assert (await alice.post(f"/projects/{project['id']}/build", json={})).json()["error"]["code"] == "BUILD_RUNNING"
    run = (await alice.get(f"/runs/{run_id}")).json()
    assert "```file:web/index.html" in run["input"]["message"]  # the file protocol reaches the team

    calls: list[str] = []
    registry.test_transport = httpx.MockTransport(_team_handler(calls))
    try:
        w = Worker(db=database, worker_id="build-test", heartbeat_interval=0.1)
        claimed = await w.runs.claim(w.id, 30)
        assert claimed["_id"] == run_id
        assert await w.process(claimed) == "completed", (await alice.get(f"/runs/{run_id}")).json()["error"]
    finally:
        registry.test_transport = None

    done = (await alice.get(f"/projects/{project['id']}")).json()
    build = done["build_runs"][0]
    assert build["status"] == "completed" and build["verdict"] == "complete"
    assert {f["path"] for f in done["files"]} == {"web/index.html", "backend/app.py"}
    assert done["status"] == "completed" and build["files_written"] == ["backend/app.py", "web/index.html"]

    # The user edits a file and asks for a change: the next round sees the current files.
    edited = await alice.req("PUT", f"/projects/{project['id']}/files",
                             json={"path": "web/index.html", "content": "<h1>Mine</h1>"})
    assert edited.status_code == 200
    assert next(f for f in edited.json()["files"] if f["path"] == "web/index.html")["content"] == "<h1>Mine</h1>"
    assert (await alice.req("PUT", f"/projects/{project['id']}/files", json={"path": "../x", "content": ""})).status_code == 422
    again = await alice.post(f"/projects/{project['id']}/build", json={"instructions": "Make the header blue"})
    assert again.status_code == 202, again.text
    msg = (await alice.get(f"/runs/{again.json()['run_id']}")).json()["input"]["message"]
    assert "<h1>Mine</h1>" in msg and "Make the header blue" in msg
    assert again.json()["workflow_id"] == started.json()["workflow_id"]
    gone = await alice.delete(f"/projects/{project['id']}/files", params={"path": "backend/app.py"})
    assert [f["path"] for f in gone.json()["files"]] == ["web/index.html"]


async def test_build_needs_a_team(alice):
    from tests.conftest import published_agent
    agent = await published_agent(alice)
    project = (await alice.post("/projects", json={"name": "No team", "idea": "Something to build here",
                                                   "planning_agent_ids": [agent["id"]]})).json()
    r = await alice.post(f"/projects/{project['id']}/build", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUILD_TEAM_INVALID"
