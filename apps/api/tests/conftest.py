"""Integration test harness: real MongoDB (replica set, for transactions), real FastAPI app
via ASGI transport, a throwaway database per test session."""
import base64
import os
import uuid

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017/?replicaSet=rs0")
os.environ["MONGODB_DB"] = f"orch_test_{uuid.uuid4().hex[:8]}"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["REGISTER_RATE_LIMIT_PER_MINUTE"] = "10000"
os.environ["ENCRYPTION_KEYS"] = base64.urlsafe_b64encode(b"test-only-key-not-for-production").decode()

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.client import close_client, get_client, get_db  # noqa: E402
from app.db.indexes import ensure_schema  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def database():
    db = get_db()
    await ensure_schema(db)
    yield db
    await get_client().drop_database(get_settings().mongodb_db)
    await close_client()


class Api:
    """Test client that behaves like the browser: cookies + CSRF header + workspace header."""

    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.workspace_id: str | None = None
        self.user_id: str | None = None

    def _headers(self, extra: dict | None = None) -> dict:
        h = {}
        csrf = self.c.cookies.get(get_settings().csrf_cookie_name)
        if csrf:
            h["X-CSRF-Token"] = csrf
        if self.workspace_id:
            h["X-Workspace-Id"] = self.workspace_id
        return {**h, **(extra or {})}

    async def req(self, method: str, url: str, *, headers: dict | None = None, **kw) -> httpx.Response:
        return await self.c.request(method, f"/api/v1{url}", headers=self._headers(headers), **kw)

    async def get(self, url, **kw):
        return await self.req("GET", url, **kw)

    async def post(self, url, **kw):
        return await self.req("POST", url, **kw)

    async def patch(self, url, **kw):
        return await self.req("PATCH", url, **kw)

    async def delete(self, url, **kw):
        return await self.req("DELETE", url, **kw)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


async def make_user(label: str = "u") -> Api:
    api = Api(_client())
    email = f"{label}-{uuid.uuid4().hex[:8]}@example.com"
    r = await api.post("/auth/register", json={"email": email, "password": "correct horse battery",
                                               "name": label, "workspace_name": f"{label} workspace"})
    assert r.status_code == 201, r.text
    body = r.json()
    api.workspace_id = body["memberships"][0]["workspace_id"]
    api.user_id = body["user"]["id"]
    api.email = email  # type: ignore[attr-defined]
    return api


@pytest.fixture
async def alice() -> Api:
    return await make_user("alice")


@pytest.fixture
async def bob() -> Api:
    return await make_user("bob")


async def demo_provider_id(api: Api) -> str:
    r = await api.get("/model-providers")
    assert r.status_code == 200, r.text
    return next(p["id"] for p in r.json() if p["kind"] == "demo")


async def published_agent(api: Api, model: str = "demo-echo", **cfg) -> dict:
    pid = await demo_provider_id(api)
    config = {"system_prompt": "You are helpful.", "model": {"provider_id": pid, "model": model}, **cfg}
    r = await api.post("/agents", json={"name": f"agent-{uuid.uuid4().hex[:6]}", "config": config})
    assert r.status_code == 201, r.text
    r = await api.post(f"/agents/{r.json()['id']}/publish", json={"note": "v1"})
    assert r.status_code == 200, r.text
    return r.json()
