import uuid

from app.core.config import get_settings
from tests.conftest import Api, _client, make_user, published_agent

PW = "correct horse battery"


async def _invite(owner: Api, email: str, role: str = "developer") -> dict:
    r = await owner.post("/workspace/invitations", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    return r.json()


async def test_invite_new_user_registers_into_workspace():
    owner = await make_user("inv-owner")
    email = f"new-{uuid.uuid4().hex[:6]}@example.com"
    inv = await _invite(owner, email)
    assert inv["url"].endswith("/invite/" + inv["token"])

    anon = Api(_client())
    info = await anon.get(f"/auth/invitations/{inv['token']}")
    assert info.status_code == 200 and info.json()["role"] == "developer" and not info.json()["has_account"]

    r = await anon.post("/auth/register", json={"email": email, "password": PW, "name": "New",
                                                "invite_token": inv["token"]})
    assert r.status_code == 201, r.text
    ms = r.json()["memberships"]
    assert [(m["workspace_id"], m["role"]) for m in ms] == [(owner.workspace_id, "developer")]

    # single use
    again = await Api(_client()).get(f"/auth/invitations/{inv['token']}")
    assert again.status_code == 404
    pending = await owner.get("/workspace/invitations")
    assert pending.json() == []


async def test_invite_existing_user_accepts():
    owner = await make_user("inv-owner2")
    other = await make_user("inv-other")
    inv = await _invite(owner, other.email, "viewer")  # type: ignore[attr-defined]
    r = await other.post(f"/auth/invitations/{inv['token']}/accept")
    assert r.status_code == 200, r.text
    assert any(m["workspace_id"] == owner.workspace_id and m["role"] == "viewer" for m in r.json()["memberships"])


async def test_invitation_email_must_match():
    owner = await make_user("inv-owner3")
    stranger = await make_user("inv-stranger")
    inv = await _invite(owner, "someone-else@example.com")
    r = await stranger.post(f"/auth/invitations/{inv['token']}/accept")
    assert r.status_code == 403 and r.json()["error"]["code"] == "INVITATION_EMAIL_MISMATCH"
    r = await Api(_client()).post("/auth/register", json={"email": "wrong@example.com", "password": PW,
                                                          "name": "x", "invite_token": inv["token"]})
    assert r.status_code == 403


async def test_invitation_role_cannot_exceed_inviter():
    owner = await make_user("inv-owner4")
    dev_email = f"dev-{uuid.uuid4().hex[:6]}@example.com"
    inv = await _invite(owner, dev_email, "developer")
    dev = Api(_client())
    await dev.post("/auth/register", json={"email": dev_email, "password": PW, "name": "d",
                                           "invite_token": inv["token"]})
    dev.workspace_id = owner.workspace_id
    r = await dev.post("/workspace/invitations", json={"email": "x@example.com", "role": "viewer"})
    assert r.status_code == 403  # developers cannot manage members at all


async def test_revoked_invitation_is_unusable():
    owner = await make_user("inv-owner5")
    inv = await _invite(owner, "revoked@example.com")
    assert (await owner.delete(f"/workspace/invitations/{inv['id']}")).status_code == 204
    assert (await Api(_client()).get(f"/auth/invitations/{inv['token']}")).status_code == 404


async def test_registration_can_be_closed():
    s = get_settings()
    s.allow_registration = False
    try:
        cfg = await Api(_client()).get("/auth/config")
        assert cfg.json()["registration_open"] is False
        r = await Api(_client()).post("/auth/register", json={"email": "closed@example.com", "password": PW,
                                                              "name": "c", "workspace_name": "w"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "REGISTRATION_CLOSED"
        owner = await _registered_owner_while_closed()
        email = f"closed-inv-{uuid.uuid4().hex[:6]}@example.com"
        inv = await _invite(owner, email)
        r = await Api(_client()).post("/auth/register", json={"email": email, "password": PW, "name": "i",
                                                              "invite_token": inv["token"]})
        assert r.status_code == 201, r.text
    finally:
        s.allow_registration = True


async def _registered_owner_while_closed() -> Api:
    s = get_settings()
    s.allow_registration = True
    try:
        return await make_user("closed-owner")
    finally:
        s.allow_registration = False


async def test_register_requires_workspace_or_invite():
    r = await Api(_client()).post("/auth/register", json={"email": "nows@example.com", "password": PW, "name": "n"})
    assert r.status_code == 422


async def test_change_password_signs_out_other_sessions():
    a = await make_user("pw")
    other = Api(_client())
    assert (await other.post("/auth/login", json={"email": a.email, "password": PW})).status_code == 200
    r = await a.post("/auth/password", json={"current_password": "wrong", "new_password": "a brand new password"})
    assert r.status_code == 401
    r = await a.post("/auth/password", json={"current_password": PW, "new_password": "a brand new password"})
    assert r.status_code == 204
    assert (await a.get("/auth/me")).status_code == 200  # current session kept
    assert (await other.get("/auth/me")).status_code == 401  # other session revoked
    r = await Api(_client()).post("/auth/login", json={"email": a.email, "password": "a brand new password"})
    assert r.status_code == 200


async def test_create_additional_workspace():
    a = await make_user("multi")
    r = await a.post("/auth/workspaces", json={"name": "Second"})
    assert r.status_code == 201
    names = {m["workspace_name"] for m in r.json()["memberships"]}
    assert "Second" in names and len(names) == 2


async def test_api_key_lifecycle_and_scope():
    owner = await make_user("key-owner")
    agent = await published_agent(owner)
    r = await owner.post("/workspace/api-keys", json={"name": "ci", "role": "operator"})
    assert r.status_code == 201, r.text
    key = r.json()["key"]
    assert key.startswith("orch_") and r.json()["prefix"] == key[:12]

    bearer = {"Authorization": f"Bearer {key}"}
    async with _client() as c:
        # no cookies, no CSRF, no workspace header needed
        r = await c.post("/api/v1/runs", json={"agent_id": agent["id"], "input": {"message": "hi"}}, headers=bearer)
        assert r.status_code == 202, r.text
        # operator role: cannot write agents
        r = await c.post("/api/v1/agents", json={"name": "nope"}, headers=bearer)
        assert r.status_code == 403
        # bound to its workspace
        other = await make_user("key-other")
        r = await c.get("/api/v1/agents", headers={**bearer, "X-Workspace-Id": other.workspace_id})
        assert r.status_code == 404
        # cannot mint keys
        r = await c.post("/api/v1/workspace/api-keys", json={"name": "x", "role": "viewer"}, headers=bearer)
        assert r.status_code == 403

    listed = (await owner.get("/workspace/api-keys")).json()
    assert len(listed) == 1 and "key" not in listed[0] and listed[0]["last_used_at"] is not None
    assert (await owner.delete(f"/workspace/api-keys/{listed[0]['id']}")).status_code == 204
    async with _client() as c:
        r = await c.get("/api/v1/agents", headers=bearer)
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_API_KEY"


async def test_api_key_role_cannot_exceed_creator(database):
    owner = await make_user("key-owner2")
    await database["workspace_members"].update_one({"workspace_id": owner.workspace_id, "user_id": owner.user_id},
                                                   {"$set": {"role": "administrator"}})
    r = await owner.post("/workspace/api-keys", json={"name": "x", "role": "owner"})
    assert r.status_code == 403


async def test_run_wait_seconds_returns_finished_run():
    owner = await make_user("wait")
    agent = await published_agent(owner)
    r = await owner.post("/runs?wait_seconds=1", json={"agent_id": agent["id"], "input": {"message": "hi"}})
    # No worker runs in the API test process, so the wait elapses with the run still queued.
    assert r.status_code == 202 and r.json()["status"] == "queued"
