"""Cross-workspace isolation and RBAC. These tests actively attempt cross-tenant access."""
from tests.conftest import demo_provider_id, make_user, published_agent


async def test_cross_workspace_reads_are_404(alice, bob):
    agent = await published_agent(alice)
    run = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "hi"}})).json()
    pid = await demo_provider_id(alice)
    for url in (f"/agents/{agent['id']}", f"/agents/{agent['id']}/versions", f"/runs/{run['id']}",
                f"/runs/{run['id']}/events", f"/runs/{run['id']}/stream", f"/model-providers/{pid}"):
        r = await bob.get(url)
        assert r.status_code == 404, (url, r.status_code)
    assert all(a["id"] != agent["id"] for a in (await bob.get("/agents")).json()["items"])
    assert all(x["id"] != run["id"] for x in (await bob.get("/runs")).json()["items"])


async def test_cross_workspace_writes_are_rejected(alice, bob):
    agent = await published_agent(alice)
    run = (await alice.post("/runs", json={"agent_id": agent["id"], "input": {"message": "hi"}})).json()
    assert (await bob.patch(f"/agents/{agent['id']}", json={"revision": agent["revision"], "name": "pwn"})
            ).status_code == 404
    assert (await bob.delete(f"/agents/{agent['id']}")).status_code == 404
    assert (await bob.post(f"/agents/{agent['id']}/publish", json={})).status_code == 404
    assert (await bob.post(f"/runs/{run['id']}/cancel")).status_code == 404
    assert (await bob.post("/runs", json={"agent_id": agent["id"], "input": {"message": "x"}})).status_code == 404
    # Bob's agent may not reference Alice's provider.
    pid = await demo_provider_id(alice)
    r = await bob.post("/agents", json={"name": "steal", "config": {"model": {"provider_id": pid, "model": "demo-echo"}}})
    assert r.status_code == 201
    r = await bob.post(f"/agents/{r.json()['id']}/publish", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PROVIDER_NOT_FOUND"


async def test_spoofed_workspace_header_is_rejected(alice, bob):
    bob.workspace_id = alice.workspace_id
    for url in ("/agents", "/runs", "/workspace", "/dashboard"):
        r = await bob.get(url)
        assert r.status_code == 404 and r.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    r = await bob.post("/agents", json={"name": "x"})
    assert r.status_code == 404
    # Query-param variant used by EventSource is verified the same way.
    bob.workspace_id = None
    r = await bob.c.get(f"/api/v1/agents?workspace_id={alice.workspace_id}")
    assert r.status_code == 404


async def test_role_permissions(alice):
    agent = await published_agent(alice)
    viewer, operator, developer = await make_user("viewer"), await make_user("operator"), await make_user("dev")
    for u, role in ((viewer, "viewer"), (operator, "operator"), (developer, "developer")):
        assert (await alice.post("/workspace/members", json={"email": u.email, "role": role})).status_code == 201
        u.workspace_id = alice.workspace_id

    run_body = {"agent_id": agent["id"], "input": {"message": "hi"}}
    assert (await viewer.get("/agents")).status_code == 200
    assert (await viewer.post("/agents", json={"name": "v"})).status_code == 403
    assert (await viewer.post("/runs", json=run_body)).status_code == 403
    assert (await viewer.get("/audit-logs")).status_code == 403

    assert (await operator.post("/runs", json=run_body)).status_code == 202
    assert (await operator.post("/runs", json={**run_body, "source": "draft"})).status_code == 403
    assert (await operator.post("/agents", json={"name": "o"})).status_code == 403

    assert (await developer.post("/agents", json={"name": "d"})).status_code == 201
    assert (await developer.post("/runs", json={**run_body, "source": "draft"})).status_code == 202
    assert (await developer.post("/model-providers", json={"kind": "openai", "name": "x", "api_key": "sk-test"})
            ).status_code == 403
    assert (await developer.post("/workspace/members", json={"email": viewer.email, "role": "owner"})
            ).status_code == 403
    assert (await alice.get("/audit-logs")).status_code == 200


async def test_cannot_escalate_or_remove_last_owner(alice):
    admin = await make_user("admin")
    await alice.post("/workspace/members", json={"email": admin.email, "role": "administrator"})
    admin.workspace_id = alice.workspace_id
    r = await admin.patch(f"/workspace/members/{admin.user_id}", json={"role": "owner"})
    assert r.status_code == 403
    r = await admin.patch(f"/workspace/members/{alice.user_id}", json={"role": "viewer"})
    assert r.status_code == 403
    r = await alice.patch(f"/workspace/members/{alice.user_id}", json={"role": "viewer"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "LAST_OWNER"


async def test_audit_log_records_actions(alice):
    await published_agent(alice)
    actions = {i["action"] for i in (await alice.get("/audit-logs", params={"limit": 200})).json()["items"]}
    assert {"auth.register", "agent.create", "agent.publish"} <= actions
