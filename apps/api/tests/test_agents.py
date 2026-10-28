from tests.conftest import demo_provider_id


async def _create(api, **cfg):
    pid = await demo_provider_id(api)
    r = await api.post("/agents", json={"name": cfg.pop("name", "Support bot"), "description": "d",
                                        "config": {"system_prompt": "v1 prompt",
                                                   "model": {"provider_id": pid, "model": "demo-echo"}, **cfg}})
    assert r.status_code == 201, r.text
    return r.json()


async def test_crud_and_optimistic_concurrency(alice):
    a = await _create(alice)
    assert a["status"] == "draft" and a["revision"] == 1 and a["draft_dirty"]
    r = await alice.patch(f"/agents/{a['id']}", json={"revision": 1, "description": "changed"})
    assert r.status_code == 200 and r.json()["revision"] == 2
    stale = await alice.patch(f"/agents/{a['id']}", json={"revision": 1, "description": "stale"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "REVISION_MISMATCH"
    assert (await alice.post("/agents", json={"name": "support BOT"})).status_code == 409
    listed = (await alice.get("/agents", params={"q": "support"})).json()
    assert listed["total"] == 1
    assert (await alice.delete(f"/agents/{a['id']}")).status_code == 204
    assert (await alice.get(f"/agents/{a['id']}")).status_code == 404
    assert (await alice.post("/agents", json={"name": "Support bot"})).status_code == 201  # name reusable


async def test_publish_versions_are_immutable(alice):
    a = await _create(alice)
    v1 = await alice.post(f"/agents/{a['id']}/publish", json={"note": "first"})
    assert v1.status_code == 200 and v1.json()["published_version"] == 1
    again = await alice.post(f"/agents/{a['id']}/publish", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "NO_CHANGES"

    cur = v1.json()
    cfg = {**cur["draft"], "system_prompt": "v2 prompt"}
    r = await alice.patch(f"/agents/{a['id']}", json={"revision": cur["revision"], "config": cfg})
    assert r.json()["draft_dirty"] is True and r.json()["published_version"] == 1
    versions = (await alice.get(f"/agents/{a['id']}/versions")).json()
    assert versions[0]["config"]["system_prompt"] == "v1 prompt"  # editing draft did not touch v1

    # A production run uses v1 even though the draft changed.
    run = (await alice.post("/runs", json={"agent_id": a["id"], "input": {"message": "x"}})).json()
    assert run["agent_version"] == 1 and run["config"]["system_prompt"] == "v1 prompt"

    v2 = await alice.post(f"/agents/{a['id']}/publish", json={"note": "second"})
    assert v2.json()["published_version"] == 2
    diff = (await alice.get(f"/agents/{a['id']}/versions/compare", params={"a": 1, "b": 2})).json()
    assert {"path": "system_prompt", "from": "v1 prompt", "to": "v2 prompt"} in diff["changes"]

    rb = await alice.post(f"/agents/{a['id']}/rollback", json={"version": 1})
    assert rb.json()["published_version"] == 1 and rb.json()["draft"]["system_prompt"] == "v1 prompt"
    assert len((await alice.get(f"/agents/{a['id']}/versions")).json()) == 2  # nothing rewritten


async def test_lifecycle_transitions(alice):
    a = await _create(alice)
    assert (await alice.post(f"/agents/{a['id']}/pause")).status_code == 409  # draft cannot pause
    await alice.post(f"/agents/{a['id']}/publish", json={})
    assert (await alice.post(f"/agents/{a['id']}/pause")).json()["status"] == "paused"
    r = await alice.post("/runs", json={"agent_id": a["id"], "input": {"message": "x"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "AGENT_NOT_RUNNABLE"
    assert (await alice.post(f"/agents/{a['id']}/resume")).json()["status"] == "published"
    assert (await alice.post(f"/agents/{a['id']}/retire")).json()["status"] == "retired"
    assert (await alice.post(f"/agents/{a['id']}/publish", json={})).status_code == 409
    assert (await alice.patch(f"/agents/{a['id']}", json={"revision": 99, "name": "z"})).status_code == 409


async def test_publish_requires_model_and_allowlist(alice):
    r = await alice.post("/agents", json={"name": "nomodel"})
    assert (await alice.post(f"/agents/{r.json()['id']}/publish", json={})).json()["error"]["code"] == "MODEL_REQUIRED"
    pid = await demo_provider_id(alice)
    r = await alice.post("/agents", json={"name": "badmodel",
                                          "config": {"model": {"provider_id": pid, "model": "gpt-not-allowed"}}})
    assert (await alice.post(f"/agents/{r.json()['id']}/publish", json={})).json()["error"]["code"] == \
        "MODEL_NOT_ALLOWED"


async def test_clone_and_validation(alice):
    a = await _create(alice)
    c = await alice.post(f"/agents/{a['id']}/clone", json={"name": "Copy"})
    assert c.status_code == 201 and c.json()["draft"] == a["draft"] and c.json()["status"] == "draft"
    bad = await alice.post("/agents", json={"name": "bad", "config": {"params": {"temperature": 5}}})
    assert bad.status_code == 422
    bad = await alice.post("/agents", json={"name": "bad2", "config": {"input_schema": {"type": "string"}}})
    assert bad.status_code == 422
    extra = await alice.post("/agents", json={"name": "bad3", "unknown_field": 1})
    assert extra.status_code == 422
