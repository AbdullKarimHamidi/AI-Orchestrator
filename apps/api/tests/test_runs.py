"""Execution lifecycle through the real worker supervisor against MongoDB."""
import asyncio
from datetime import timedelta

import httpx

from app.providers import registry
from app.repositories.base import now
from app.workers.main import Worker
from tests.conftest import demo_provider_id, published_agent


def worker(db) -> Worker:
    return Worker(db=db, worker_id="test-worker", heartbeat_interval=0.1)


async def claim_and_process(db, run_id: str) -> str:
    w = worker(db)
    run = await w.runs.claim(w.id, 30)
    assert run and run["_id"] == run_id, "expected to claim the run just created"
    return await w.process(run)


async def drain(db):
    """Cancel any leftover queued runs from other tests so claims are deterministic."""
    await db["runs"].update_many({"status": "queued"}, {"$set": {"status": "cancelled"}})


async def test_run_completes_and_records_usage(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    r = await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "ping"}})
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["demo"] is True
    assert await claim_and_process(database, r.json()["id"]) == "completed"
    run = (await alice.get(f"/runs/{r.json()['id']}")).json()
    assert run["status"] == "completed" and run["output"]["text"].startswith("[DEMO]")
    assert run["usage"]["input_tokens"] > 0 and run["duration_ms"] is not None
    types = [e["type"] for e in (await alice.get(f"/runs/{run['id']}/events")).json()]
    assert types == ["run.queued", "run.started", "model.request", "model.response", "run.completed"]
    seqs = [e["seq"] for e in (await alice.get(f"/runs/{run['id']}/events")).json()]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert await database["usage_records"].count_documents({"run_id": run["id"]}) == 1
    dash = (await alice.get("/dashboard")).json()
    assert dash["runs_by_status"]["completed"] >= 1 and dash["demo_runs"] >= 1


async def test_sse_stream_replays_and_resumes(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "s"}})).json()["id"]
    await claim_and_process(database, rid)
    body = (await alice.get(f"/runs/{rid}/stream")).text
    assert body.count("event: run_event") == 5 and "event: end" in body and '"status": "completed"' in body
    resumed = (await alice.get(f"/runs/{rid}/stream", headers={"Last-Event-ID": "3"})).text
    assert resumed.count("event: run_event") == 2 and "id: 4" in resumed


async def test_idempotency_key(alice, database):
    agent = await published_agent(alice)
    body = {"agent_id": agent["id"], "input": {"message": "once"}}
    a = await alice.post("/runs", json=body, headers={"Idempotency-Key": "k-123"})
    b = await alice.post("/runs", json=body, headers={"Idempotency-Key": "k-123"})
    assert a.status_code == 202 and b.status_code == 200 and a.json()["id"] == b.json()["id"]
    assert await database["runs"].count_documents({"workspace_id": alice.workspace_id,
                                                   "idempotency_key": "k-123"}) == 1


async def test_fallback_chain(alice, database):
    await drain(database)
    pid = await demo_provider_id(alice)
    agent = await published_agent(alice, model="demo-fail", fallbacks=[{"provider_id": pid, "model": "demo-echo"}])
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "fb"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await alice.get(f"/runs/{rid}")).json()
    assert run["output"]["slot"] == "fallback_1"
    ev = (await alice.get(f"/runs/{rid}/events")).json()
    err = next(e for e in ev if e["type"] == "model.error")
    assert err["data"]["will_fallback"] is True
    assert await database["usage_records"].count_documents({"run_id": rid}) == 2  # both attempts recorded


async def test_all_providers_fail(alice, database):
    await drain(database)
    agent = await published_agent(alice, model="demo-fail")
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).json()["id"]
    assert await claim_and_process(database, rid) == "failed"
    assert (await alice.get(f"/runs/{rid}")).json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


async def test_cancel_queued_run(alice):
    agent = await published_agent(alice)
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).json()["id"]
    r = await alice.post(f"/runs/{rid}/cancel")
    assert r.json()["status"] == "cancelled"
    assert (await alice.post(f"/runs/{rid}/cancel")).status_code == 409


async def test_cancel_running_run_stops_provider_call(alice, database):
    """Real cancellation: the in-flight provider call is interrupted, not just relabeled."""
    await drain(database)
    agent = await published_agent(alice, model="demo-slow")
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "slow"}})).json()["id"]
    w = worker(database)
    run = await w.runs.claim(w.id, 30)
    task = asyncio.create_task(w.process(run))
    await asyncio.sleep(0.4)
    assert (await alice.get(f"/runs/{rid}")).json()["status"] == "running"
    t0 = asyncio.get_running_loop().time()
    assert (await alice.post(f"/runs/{rid}/cancel")).json()["cancel_requested"] is True
    assert await asyncio.wait_for(task, timeout=5) == "cancelled"
    assert asyncio.get_running_loop().time() - t0 < 2.0  # demo-slow would otherwise take 60s
    final = (await alice.get(f"/runs/{rid}")).json()
    assert final["status"] == "cancelled" and final["error"]["code"] == "CANCELLED"


async def test_cancellation_interrupts_http_request(alice, database):
    """Cancellation propagates into an in-flight httpx request to a real provider adapter."""
    await drain(database)
    started, finished = asyncio.Event(), {"done": False}

    async def slow_handler(req):
        started.set()
        await asyncio.sleep(30)
        finished["done"] = True
        return httpx.Response(200, json={})

    p = (await alice.post("/model-providers", json={"kind": "openai", "name": "slow-openai",
                                                    "api_key": "sk-test-0000"})).json()
    agent = (await alice.post("/agents", json={"name": "slow-http", "config": {
        "model": {"provider_id": p["id"], "model": "gpt-x"}}})).json()
    await alice.post(f"/agents/{agent['id']}/publish", json={})
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).json()["id"]
    registry.test_transport = httpx.MockTransport(slow_handler)
    try:
        w = worker(database)
        task = asyncio.create_task(w.process(await w.runs.claim(w.id, 30)))
        await asyncio.wait_for(started.wait(), 5)
        await alice.post(f"/runs/{rid}/cancel")
        assert await asyncio.wait_for(task, timeout=5) == "cancelled"
        assert finished["done"] is False
    finally:
        registry.test_transport = None


async def test_timeout(alice, database):
    await drain(database)
    agent = await published_agent(alice, model="demo-slow")
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "t"}})).json()["id"]
    await database["runs"].update_one({"_id": rid}, {"$set": {"timeout_seconds": 1}})
    assert await asyncio.wait_for(claim_and_process(database, rid), timeout=6) == "timed_out"
    assert (await alice.get(f"/runs/{rid}")).json()["error"]["code"] == "TIMEOUT"


async def test_lease_recovery_after_worker_crash(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "crash"}})).json()["id"]
    crashed = worker(database)
    crashed.id = "crashed-worker"
    await crashed.runs.claim(crashed.id, 30)  # claimed, then the process "dies" (never heartbeats)
    await database["runs"].update_one({"_id": rid}, {"$set": {"lease_expires_at": now() - timedelta(seconds=1)}})
    w = worker(database)
    assert await w.recover_expired() >= 1
    doc = await database["runs"].find_one({"_id": rid})
    assert doc["status"] == "queued" and doc["lease_owner"] is None and doc["attempt"] == 1
    await database["runs"].update_one({"_id": rid}, {"$set": {"available_at": now()}})
    assert await claim_and_process(database, rid) == "completed"
    assert (await database["runs"].find_one({"_id": rid}))["attempt"] == 2
    # Stale worker can no longer write after losing the lease.
    assert await crashed.runs.finish(rid, crashed.id, {"status": "failed"}) is False


async def test_lease_recovery_exhausted_attempts(alice, database):
    await drain(database)
    agent = await published_agent(alice)
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).json()["id"]
    await database["runs"].update_one({"_id": rid}, {"$set": {
        "status": "running", "attempt": 2, "lease_owner": "dead", "lease_expires_at": now() - timedelta(seconds=1)}})
    await worker(database).recover_expired()
    doc = await database["runs"].find_one({"_id": rid})
    assert doc["status"] == "failed" and doc["error"]["code"] == "WORKER_LOST"


async def test_budget_enforced(alice, database):
    agent = await published_agent(alice)
    assert (await alice.patch("/workspace", json={"monthly_budget_usd": 0})).status_code == 200
    r = await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "BUDGET_EXCEEDED"
    await alice.patch("/workspace", json={"monthly_budget_usd": None})
    assert (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).status_code == 202


async def test_input_and_output_schema(alice, database):
    await drain(database)
    agent = await published_agent(alice, input_schema={"type": "object", "required": ["lang"],
                                                        "properties": {"lang": {"type": "string"}}},
                                  output_schema={"type": "object", "required": ["answer"]})
    r = await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x", "variables": {}}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INPUT_SCHEMA_MISMATCH"
    r = await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x", "variables": {"lang": "en"}}})
    assert await claim_and_process(database, r.json()["id"]) == "failed"  # demo text is not JSON
    assert (await alice.get(f"/runs/{r.json()['id']}")).json()["error"]["code"] == "OUTPUT_SCHEMA_MISMATCH"


async def test_secrets_redacted_from_events(alice, database):
    await drain(database)

    def h(req):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided: sk-live-abcdefghijklmnop"}})

    p = (await alice.post("/model-providers", json={"kind": "openai", "name": "leaky", "api_key": "sk-x-0000"})).json()
    agent = (await alice.post("/agents", json={"name": "leaky", "config": {
        "model": {"provider_id": p["id"], "model": "gpt-x"}}})).json()
    await alice.post(f"/agents/{agent['id']}/publish", json={})
    rid = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).json()["id"]
    registry.test_transport = httpx.MockTransport(h)
    try:
        assert await claim_and_process(database, rid) == "failed"
    finally:
        registry.test_transport = None
    events = (await alice.get(f"/runs/{rid}/events")).text
    assert "sk-live-abcdefghijklmnop" not in events and "[REDACTED]" in events
