"""Tools (HTTP + MCP), knowledge ingestion/retrieval, and the agent tool loop, end to end through
the API and the real worker, with outbound HTTP mocked."""
import json

import httpx
import pytest

from app.core.config import get_settings
from app.knowledge.parsing import chunk_text, extract_text
from app.providers import registry
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ChatMessage, ChatRequest, ProviderConfig, ToolCall, ToolSpec
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter
from app.tools import http_tool
from app.tools.http_tool import ToolExecutionError, assert_public_host, render_request
from app.workers.main import Worker
from tests.conftest import demo_provider_id, make_user
from tests.test_runs import claim_and_process, drain


def _mock(handler):
    return httpx.MockTransport(handler)


@pytest.fixture
def outbound():
    """Routes all tool/MCP HTTP to a handler set by the test."""
    state: dict = {"handler": lambda req: httpx.Response(404)}
    http_tool.test_transport = _mock(lambda req: state["handler"](req))
    yield state
    http_tool.test_transport = None


WEATHER = {"name": "weather", "description": "Current weather for a city", "kind": "http",
           "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
           "http": {"method": "GET", "url": "https://api.example.com/weather/{city}"},
           "secret_headers": {"Authorization": "Bearer sk-secret-weather-123456"}}


# ---------- unit: request rendering, SSRF guard, parsing ----------

def test_render_request_places_arguments():
    m, url, q, body = render_request({"method": "GET", "url": "https://x.io/u/{id}"}, {"id": "a b", "page": 2})
    assert (m, url, q, body) == ("GET", "https://x.io/u/a%20b", {"page": 2}, None)
    m, url, q, body = render_request({"method": "POST", "url": "https://x.io/items"}, {"name": "n"})
    assert body == {"name": "n"} and q is None
    with pytest.raises(ToolExecutionError):
        render_request({"method": "GET", "url": "https://x.io/{missing}"}, {})


async def test_ssrf_guard_blocks_private_addresses():
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/",
                "http://localhost:8000/", "ftp://example.com/"):
        with pytest.raises(ToolExecutionError):
            await assert_public_host(url)
    s = get_settings()
    s.tools_allow_private_networks = True
    try:
        await assert_public_host("http://127.0.0.1/x")
    finally:
        s.tools_allow_private_networks = False


def test_extract_and_chunk():
    html = b"<html><script>evil()</script><h1>Title</h1><p>Hello&nbsp;world</p></html>"
    assert extract_text("a.html", html) == "Title\n Hello world" or "Hello world" in extract_text("a.html", html)
    assert "evil" not in extract_text("a.html", html)
    csv_text = extract_text("t.csv", b"name,age\nAda,36\n")
    assert "name: Ada" in csv_text and "age: 36" in csv_text
    text = "\n\n".join(f"Paragraph {i} " + "word " * 80 for i in range(20))
    chunks = chunk_text(text, 1000, 100)
    assert len(chunks) > 5 and all(len(c) <= 1200 for c in chunks)
    with pytest.raises(ValueError):
        extract_text("x.exe", b"MZ")


# ---------- unit: provider tool-call wire formats ----------

def _conv() -> ChatRequest:
    call = ToolCall("c1", "weather", {"city": "Kabul"})
    return ChatRequest(model="m", system="s", tools=[ToolSpec("weather", "d", {"type": "object"})], messages=[
        ChatMessage("user", "hi"), ChatMessage("assistant", "", tool_calls=[call]),
        ChatMessage("tool", "sunny", tool_call_id="c1", name="weather")])


def test_openai_tool_wire_format():
    body = OpenAIAdapter(ProviderConfig("openai", "k", None, 5)).build_body(_conv())
    assert body["tools"][0]["function"]["name"] == "weather"
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == json.dumps({"city": "Kabul"})
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "sunny"}


def test_anthropic_tool_wire_format():
    body = AnthropicAdapter(ProviderConfig("anthropic", "k", None, 5)).build_body(_conv())
    assert body["tools"][0]["input_schema"] == {"type": "object"}
    assert body["messages"][1]["content"][0]["type"] == "tool_use"
    assert body["messages"][2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c1", "content": "sunny"}]}


def test_gemini_tool_wire_format():
    body = GeminiAdapter(ProviderConfig("gemini", "k", None, 5)).build_body(_conv())
    assert body["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"] == {"type": "object"}
    assert body["contents"][1]["parts"][0]["functionCall"]["name"] == "weather"
    assert body["contents"][2]["parts"][0]["functionResponse"] == {"name": "weather",
                                                                  "response": {"result": "sunny"}}


async def test_openai_parses_tool_calls():
    def h(req):
        return httpx.Response(200, json={"id": "x", "choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": "call_1", "type": "function",
                                             "function": {"name": "weather", "arguments": "{\"city\":\"Herat\"}"}}]}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    res = await OpenAIAdapter(ProviderConfig("openai", "k", None, 5), transport=_mock(h)).chat(_conv())
    assert res.tool_calls[0].arguments == {"city": "Herat"} and res.text == ""


# ---------- API: tools ----------

async def test_tool_crud_hides_secrets_and_tests(alice, outbound):
    seen = {}

    def h(req: httpx.Request):
        seen["url"], seen["auth"] = str(req.url), req.headers.get("authorization")
        return httpx.Response(200, json={"temp_c": 21})
    outbound["handler"] = h
    r = await alice.post("/tools", json=WEATHER)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["secret_header_names"] == ["Authorization"] and "sk-secret" not in r.text
    r = await alice.post(f"/tools/{t['id']}/test", json={"arguments": {"city": "Kabul"}})
    assert r.json()["ok"] is True and "21" in r.json()["output"]
    assert seen == {"url": "https://api.example.com/weather/Kabul", "auth": "Bearer sk-secret-weather-123456"}
    r = await alice.post(f"/tools/{t['id']}/test", json={"arguments": {}})
    assert r.json()["ok"] is False and "invalid arguments" in r.json()["error"]
    assert (await alice.post("/tools", json=WEATHER)).status_code == 409
    assert (await alice.post("/tools", json={**WEATHER, "name": "knowledge_search"})).status_code == 409
    assert (await alice.delete(f"/tools/{t['id']}")).status_code == 204
    assert (await alice.get(f"/tools/{t['id']}")).status_code == 404


async def test_viewer_cannot_write_tools(alice, bob, database):
    await database["workspace_members"].update_one({"workspace_id": bob.workspace_id, "user_id": bob.user_id},
                                                   {"$set": {"role": "viewer"}})
    assert (await bob.get("/tools")).status_code == 200
    assert (await bob.post("/tools", json=WEATHER)).status_code == 403


def _mcp_handler(calls: list):
    def h(req: httpx.Request):
        msg = json.loads(req.content)
        calls.append(msg.get("method"))
        if "id" not in msg:
            return httpx.Response(202)
        if msg["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "x"}},
                                  headers={"Mcp-Session-Id": "sess-1"})
        if msg["method"] == "tools/list":
            assert req.headers.get("mcp-session-id") == "sess-1"
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
                {"name": "lookup_order", "description": "Find an order",
                 "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}}}}]}})
        if msg["method"] == "tools/call":
            # answer as an SSE stream, like many Streamable HTTP servers do
            payload = {"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": f"order {msg['params']['arguments'].get('order_id')}: shipped"}]}}
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(payload)}\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(400)
    return h


async def test_mcp_discover_import_and_call(alice, outbound):
    calls: list = []
    outbound["handler"] = _mcp_handler(calls)
    r = await alice.post("/tools/mcp/discover", json={"server_url": "https://mcp.example.com/mcp"})
    assert r.status_code == 200 and r.json()[0]["name"] == "lookup_order"
    r = await alice.post("/tools/mcp/import", json={"server_url": "https://mcp.example.com/mcp",
                                                     "tools": ["lookup_order"], "name_prefix": "shop_"})
    assert r.status_code == 201, r.text
    tool = r.json()[0]
    assert tool["name"] == "shop_lookup_order" and tool["kind"] == "mcp"
    r = await alice.post(f"/tools/{tool['id']}/test", json={"arguments": {"order_id": "A1"}})
    assert r.json() == {**r.json(), "ok": True, "output": "order A1: shipped"}
    assert "notifications/initialized" in calls


# ---------- agent tool loop through the worker ----------

async def test_agent_calls_tool_through_worker(alice, database, outbound):
    await drain(database)
    outbound["handler"] = lambda req: httpx.Response(200, json={"temp_c": 30, "city": req.url.path.rsplit("/", 1)[-1]})
    tool = (await alice.post("/tools", json={**WEATHER, "name": "weather_loop"})).json()
    pid = await demo_provider_id(alice)
    a = (await alice.post("/agents", json={"name": "tool-agent", "config": {
        "model": {"provider_id": pid, "model": "demo-tools"}, "tool_ids": [tool["id"]]}})).json()
    assert (await alice.post(f"/agents/{a['id']}/publish", json={"note": "v1"})).status_code == 200
    rid = (await alice.post("/runs", json={"agent_id": a["id"], "input": {"message": "Kabul"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await alice.get(f"/runs/{rid}")).json()
    assert run["output"]["tool_calls"] == 1 and "temp_c" in run["output"]["text"]
    types = [e["type"] for e in (await alice.get(f"/runs/{rid}/events")).json()]
    assert types == ["run.queued", "run.started", "model.request", "model.response", "tool.call", "tool.result",
                     "model.request", "model.response", "run.completed"]
    assert await database["usage_records"].count_documents({"run_id": rid}) == 2


async def test_tool_limit_forces_final_answer(alice, database, outbound):
    await drain(database)
    outbound["handler"] = lambda req: httpx.Response(200, text="ok")
    tool = (await alice.post("/tools", json={**WEATHER, "name": "weather_limit"})).json()
    pid = await demo_provider_id(alice)
    a = (await alice.post("/agents", json={"name": "limited", "config": {
        "model": {"provider_id": pid, "model": "demo-tools"}, "tool_ids": [tool["id"]],
        "limits": {"max_tool_calls": 0}}})).json()
    rid = (await alice.post("/runs", json={"agent_id": a["id"], "source": "draft",
                                           "input": {"message": "x"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await alice.get(f"/runs/{rid}")).json()
    assert run["output"]["tool_calls"] == 0  # tools were never offered


async def test_publish_rejects_unknown_tool(alice):
    pid = await demo_provider_id(alice)
    a = (await alice.post("/agents", json={"name": "bad-tools", "config": {
        "model": {"provider_id": pid, "model": "demo-echo"}, "tool_ids": ["tol_nope"]}})).json()
    r = await alice.post(f"/agents/{a['id']}/publish", json={"note": "v1"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TOOL_NOT_FOUND"


# ---------- knowledge ----------

async def _ingest_all(db) -> None:
    w = Worker(db=db, worker_id="ingest-test")
    while await w.ingest_one():
        pass


async def test_knowledge_upload_ingest_search_and_rag(database):
    api = await make_user("kb")
    kb = (await api.post("/knowledge-bases", json={"name": "Handbook"})).json()
    files = {"file": ("vacation.md", b"# Vacation policy\n\nEmployees get 24 paid vacation days per year.\n\n"
                                     b"# Expenses\n\nMeals are reimbursed up to 30 USD per day.", "text/markdown")}
    r = await api.c.post(f"/api/v1/knowledge-bases/{kb['id']}/documents/upload", files=files,
                         headers=api._headers())
    assert r.status_code == 202, r.text
    doc = r.json()
    assert doc["status"] == "queued"
    r = await api.post(f"/knowledge-bases/{kb['id']}/documents/text",
                       json={"title": "Security", "text": "Laptops must use full disk encryption."})
    assert r.status_code == 202
    await _ingest_all(database)
    docs = (await api.get("/documents", params={"kb_id": kb["id"]})).json()["items"]
    assert {d["status"] for d in docs} == {"ready"} and all(d["chunk_count"] >= 1 for d in docs)
    assert (await api.get(f"/knowledge-bases/{kb['id']}")).json()["doc_count"] == 2

    hits = (await api.post(f"/knowledge-bases/{kb['id']}/search",
                           json={"query": "how many vacation days", "top_k": 1})).json()
    assert hits and "24 paid vacation days" in hits[0]["text"]

    # an agent with the knowledge base answers with retrieved context and citations
    await drain(database)
    pid = await demo_provider_id(api)
    a = (await api.post("/agents", json={"name": "hr-bot", "config": {
        "model": {"provider_id": pid, "model": "demo-echo"}, "knowledge_base_ids": [kb["id"]],
        "knowledge_top_k": 2}})).json()
    assert (await api.post(f"/agents/{a['id']}/publish", json={"note": "v1"})).status_code == 200
    rid = (await api.post("/runs", json={"agent_id": a["id"],
                                         "input": {"message": "vacation days per year?"}})).json()["id"]
    assert await claim_and_process(database, rid) == "completed"
    run = (await api.get(f"/runs/{rid}")).json()
    assert run["output"]["citations"][0]["title"] in ("vacation.md", "Security")
    assert "Retrieved context" in run["output"]["text"]
    ev = [e for e in (await api.get(f"/runs/{rid}/events")).json() if e["type"] == "knowledge.retrieved"]
    assert ev and ev[0]["data"]["count"] >= 1

    # deleting a document removes its chunks
    assert (await api.delete(f"/documents/{doc['id']}")).status_code == 204
    assert await database["chunks"].count_documents({"doc_id": doc["id"]}) == 0


async def test_knowledge_isolated_between_workspaces(alice, bob):
    kb = (await alice.post("/knowledge-bases", json={"name": "Private"})).json()
    assert (await bob.get(f"/knowledge-bases/{kb['id']}")).status_code == 404
    assert (await bob.post(f"/knowledge-bases/{kb['id']}/search", json={"query": "x"})).status_code == 404
    r = await bob.post(f"/knowledge-bases/{kb['id']}/documents/text", json={"title": "t", "text": "x"})
    assert r.status_code == 404


async def test_unsupported_upload_rejected(alice):
    kb = (await alice.post("/knowledge-bases", json={"name": "Files"})).json()
    r = await alice.c.post(f"/api/v1/knowledge-bases/{kb['id']}/documents/upload",
                           files={"file": ("tool.exe", b"MZ", "application/octet-stream")}, headers=alice._headers())
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT"


async def test_embedding_provider_must_support_embeddings(alice):
    r = await alice.post("/model-providers", json={"kind": "anthropic", "name": "claude", "api_key": "sk-ant-xyz12345"})
    assert r.status_code == 201, r.text
    r = await alice.post("/knowledge-bases", json={"name": "Vec", "embedding": {
        "provider_id": r.json()["id"], "model": "x"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "NO_EMBEDDINGS"


async def test_openai_embeddings_used_for_ingest_and_search(alice, database):
    def h(req: httpx.Request):
        body = json.loads(req.content)
        vec = lambda t: [1.0, 0.0] if "cat" in t else [0.0, 1.0]  # noqa: E731
        return httpx.Response(200, json={"data": [{"index": i, "embedding": vec(t)} for i, t in enumerate(body["input"])]})
    registry.test_transport = _mock(h)
    from app.knowledge import embeddings
    orig = embeddings._OpenAIEmbeddings.__init__

    def init(self, cfg, transport=None):
        orig(self, cfg, transport=registry.test_transport)
    embeddings._OpenAIEmbeddings.__init__ = init  # type: ignore[method-assign]
    try:
        p = (await alice.post("/model-providers", json={"kind": "openai", "name": "oa-emb",
                                                        "api_key": "sk-test-1234567890"})).json()
        kb = (await alice.post("/knowledge-bases", json={"name": "Vectors", "embedding": {
            "provider_id": p["id"], "model": "text-embedding-3-small"}})).json()
        await alice.post(f"/knowledge-bases/{kb['id']}/documents/text", json={"title": "pets", "text": "the cat sat"})
        await alice.post(f"/knowledge-bases/{kb['id']}/documents/text", json={"title": "cars", "text": "fast engines"})
        await _ingest_all(database)
        hits = (await alice.post(f"/knowledge-bases/{kb['id']}/search", json={"query": "a cat", "top_k": 1})).json()
        assert hits[0]["title"] == "pets" and hits[0]["score"] > 0.99
    finally:
        embeddings._OpenAIEmbeddings.__init__ = orig  # type: ignore[method-assign]
        registry.test_transport = None


def test_lexical_vectors_match_word_forms():
    import numpy as np

    from app.knowledge.embeddings import lexical_vector

    doc = lexical_vector("Refunds are processed within 14 days. Shipping is free.")
    assert float(np.dot(doc, lexical_vector("How long does a refund take?"))) > 0
    assert float(np.dot(doc, lexical_vector("ship"))) > 0
    assert float(np.dot(doc, lexical_vector("the of and"))) == 0
