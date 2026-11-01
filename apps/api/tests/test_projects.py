from tests.conftest import published_agent


async def test_project_can_be_deleted_even_when_planning_never_started(alice):
    agent = await published_agent(alice)
    created = await alice.post("/projects", json={
        "name": "Project to remove",
        "idea": "Build a small example application for testing project deletion",
        "planning_agent_ids": [agent["id"]],
    })
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    deleted = await alice.delete(f"/projects/{project_id}")
    assert deleted.status_code == 204, deleted.text
    assert all(p["id"] != project_id for p in (await alice.get("/projects")).json()["items"])
    assert (await alice.get(f"/projects/{project_id}")).status_code == 404


# --- Planning on the provider the user picks (regression: OpenRouter chosen, Gemini error shown) ---

import httpx  # noqa: E402

from app.providers import registry  # noqa: E402
from app.workers.main import Worker  # noqa: E402


def _provider_handler(calls: list[str]):
    """Gemini rejects every request (as with a missing/invalid key); OpenRouter answers."""
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        if "googleapis" in req.url.host:
            return httpx.Response(404, json={"error": {"message": "models/gemini-3.8-flash is not found"}})
        return httpx.Response(200, json={"id": "gen-1", "model": "x", "choices": [{
            "index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "# Plan\nBuild it."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    return handler


async def _process_all(db, run_ids: list[str]) -> None:
    w = Worker(db=db, worker_id="project-test-worker", heartbeat_interval=0.1)
    # Other tests may leave queued runs behind; only process ours.
    await db["runs"].update_many({"status": "queued", "_id": {"$nin": run_ids}}, {"$set": {"status": "cancelled"}})
    for _ in run_ids:
        run = await w.runs.claim(w.id, 30)
        assert run and run["_id"] in run_ids
        await w.process(run)


async def _gemini_agent_edited_to_openrouter(api):
    """An agent published on Gemini whose draft was then switched to OpenRouter (not republished)."""
    gemini = (await api.post("/model-providers/presets/gemini", json={"api_key": "AIza-test-key"})).json()
    openrouter = (await api.post("/model-providers/presets/openrouter", json={"api_key": "sk-or-test"})).json()
    agent = (await api.post("/agents", json={"name": "Idea Generator", "config": {
        "system_prompt": "Brainstorm.", "model": {"provider_id": gemini["id"], "model": "gemini-3.8-flash"}}})).json()
    assert (await api.post(f"/agents/{agent['id']}/publish", json={"note": "v1"})).status_code == 200
    agent = (await api.get(f"/agents/{agent['id']}")).json()
    r = await api.patch(f"/agents/{agent['id']}", json={"revision": agent["revision"], "config": agent["draft"] | {
        "model": {"provider_id": openrouter["id"], "model": "meta-llama/llama-3.3-70b-instruct:free"}}})
    assert r.status_code == 200, r.text
    return agent, gemini, openrouter


async def test_project_planning_runs_on_the_selected_provider(alice, database):
    agent, gemini, openrouter = await _gemini_agent_edited_to_openrouter(alice)
    created = await alice.post("/projects", json={
        "name": "OpenRouter project", "idea": "Build a task tracker for a small team with reminders",
        "planning_agent_ids": [agent["id"]],
        "planning_model": {"provider_id": openrouter["id"], "model": "meta-llama/llama-3.3-70b-instruct:free"}})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["planning_model"]["provider_id"] == openrouter["id"]
    assert project["planning_model"]["provider_name"] == "OpenRouter (free models)"

    # The plan request with no body fields (what the UI sends first) must be accepted.
    started = await alice.post(f"/projects/{project['id']}/plan", json={"feedback": ""})
    assert started.status_code == 202, started.text
    run_ids = started.json()["run_ids"]
    run = (await alice.get(f"/runs/{run_ids[0]}")).json()
    assert run["config"]["model"]["provider_id"] == openrouter["id"] and run["config"]["fallbacks"] == []
    assert run["config"]["system_prompt"] == "Brainstorm."

    calls: list[str] = []
    registry.test_transport = httpx.MockTransport(_provider_handler(calls))
    try:
        await _process_all(database, run_ids)
    finally:
        registry.test_transport = None
    assert calls == ["openrouter.ai"]
    done = (await alice.get(f"/projects/{project['id']}")).json()
    assert done["planning_runs"][0]["status"] == "completed"
    assert done["status"] == "ready" and "Build it." in done["documents"][0]["content"]

    # Revising with feedback keeps the chosen provider.
    again = await alice.post(f"/projects/{project['id']}/plan", json={"feedback": "Add an admin panel"})
    assert again.status_code == 202, again.text
    run = (await alice.get(f"/runs/{again.json()['run_ids'][0]}")).json()
    assert run["config"]["model"]["provider_id"] == openrouter["id"]


async def test_project_planning_error_names_the_failing_provider(alice, database):
    agent, gemini, _ = await _gemini_agent_edited_to_openrouter(alice)
    project = (await alice.post("/projects", json={
        "name": "Default model project", "idea": "Build a recipe sharing site with comments",
        "planning_agent_ids": [agent["id"]]})).json()
    assert project["planning_model"] is None
    run_ids = (await alice.post(f"/projects/{project['id']}/plan", json={})).json()["run_ids"]
    registry.test_transport = httpx.MockTransport(_provider_handler([]))
    try:
        await _process_all(database, run_ids)
    finally:
        registry.test_transport = None
    failed = (await alice.get(f"/projects/{project['id']}")).json()
    assert failed["status"] == "blocked"
    assert "Google Gemini (free tier) (gemini-3.8-flash)" in str(failed["planning_runs"][0]["error"])

    # Switching the project to OpenRouter on the next plan request fixes it without republishing.
    r = await alice.post(f"/projects/{project['id']}/plan", json={
        "planning_model": {"provider_id": _["id"], "model": "meta-llama/llama-3.3-70b-instruct:free"}})
    assert r.status_code == 202, r.text
    assert (await alice.get(f"/projects/{project['id']}")).json()["planning_model"]["provider_id"] == _["id"]


async def test_planning_model_must_be_a_usable_workspace_provider(alice, bob):
    agent = await published_agent(alice)
    other = (await bob.post("/model-providers/presets/groq", json={"api_key": "gsk_bob_key"})).json()
    r = await alice.post("/projects", json={
        "name": "Bad provider", "idea": "Build something useful for testing",
        "planning_agent_ids": [agent["id"]], "planning_model": {"provider_id": other["id"], "model": "x"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PROVIDER_NOT_FOUND"
