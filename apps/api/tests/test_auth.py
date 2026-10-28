from app.core.config import get_settings
from tests.conftest import Api, _client, make_user


async def test_register_me_logout_login():
    api = await make_user("carol")
    me = await api.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["memberships"][0]["role"] == "owner"
    assert "password_hash" not in me.text
    assert (await api.post("/auth/logout")).status_code == 204
    assert (await api.get("/auth/me")).status_code == 401
    r = await api.post("/auth/login", json={"email": api.email, "password": "correct horse battery"})
    assert r.status_code == 200
    assert (await api.get("/auth/me")).status_code == 200


async def test_session_cookie_flags():
    api = Api(_client())
    r = await api.post("/auth/register", json={"email": "flags@example.com", "password": "correct horse battery",
                                               "name": "f", "workspace_name": "w"})
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(get_settings().session_cookie_name + "="))
    assert "HttpOnly" in session and "SameSite=lax" in session


async def test_password_stored_hashed(database):
    api = await make_user("hash")
    u = await database["users"].find_one({"_id": api.user_id})
    assert u["password_hash"].startswith("$argon2id$")
    assert "correct horse" not in u["password_hash"]


async def test_bad_credentials_and_duplicates():
    api = await make_user("dup")
    r = await Api(_client()).post("/auth/login", json={"email": api.email, "password": "wrong password!!"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = await Api(_client()).post("/auth/register", json={"email": api.email, "password": "correct horse battery",
                                                          "name": "x", "workspace_name": "y"})
    assert r.status_code == 409


async def test_weak_password_rejected():
    r = await Api(_client()).post("/auth/register", json={"email": "weak@example.com", "password": "short",
                                                          "name": "x", "workspace_name": "y"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unauthenticated_is_401():
    api = Api(_client())
    for url in ("/agents", "/runs", "/model-providers", "/dashboard"):
        assert (await api.get(url)).status_code == 401


async def test_csrf_required_for_mutations():
    api = await make_user("csrf")
    r = await api.c.post("/api/v1/agents", json={"name": "x"}, headers={"X-Workspace-Id": api.workspace_id})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    r = await api.c.post("/api/v1/agents", json={"name": "x"},
                         headers={"X-Workspace-Id": api.workspace_id, "X-CSRF-Token": "forged"})
    assert r.status_code == 403


async def test_login_rate_limited():
    api = await make_user("rl")
    anon = Api(_client())
    codes = [(await anon.post("/auth/login", json={"email": api.email, "password": "nope-nope-nope"})).status_code
             for _ in range(get_settings().login_rate_limit_per_minute + 1)]
    assert codes[-1] == 429


async def test_body_size_limit():
    api = await make_user("big")
    r = await api.post("/agents", content=b"x" * (get_settings().max_request_bytes + 10),
                       headers={"Content-Type": "application/json"})
    assert r.status_code == 413


async def test_health():
    api = Api(_client())
    assert (await api.get("/health/live")).status_code == 200
    r = await api.get("/health/ready")
    assert r.status_code == 200 and r.json()["mongodb"] == "ok"


def test_cors_origins_accepts_comma_separated_env(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_worker_heartbeat_healthcheck(tmp_path, monkeypatch):
    import os
    import time

    from app.workers import main as worker_main

    hb = tmp_path / "hb"
    monkeypatch.setattr(worker_main, "HEARTBEAT_FILE", str(hb))
    worker_main.touch_heartbeat()
    assert hb.exists() and time.time() - os.path.getmtime(hb) < 5
