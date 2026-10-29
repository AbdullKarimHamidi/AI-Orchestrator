"""Adapter wire formats (offline via httpx.MockTransport) and credential handling."""
import json

import httpx
import pytest

from app.providers import registry
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ChatMessage, ChatRequest, ProviderConfig, ProviderError, ToolCall, ToolSpec
from app.providers.gemini import GeminiAdapter
from app.providers.openai import OpenAIAdapter, OpenAICompatibleAdapter

REQ = ChatRequest(model="m1", messages=[ChatMessage("user", "hello")], system="be brief", max_output_tokens=50,
                  temperature=0.2)


def cfg(kind, base=None):
    return ProviderConfig(kind=kind, api_key="sk-secret-test-key-1234", base_url=base, timeout_seconds=5)


def mock(handler):
    return httpx.MockTransport(handler)


async def test_openai_request_and_usage():
    seen = {}

    def h(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json={"id": "c1", "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 2}})

    r = await OpenAIAdapter(cfg("openai"), transport=mock(h)).chat(REQ)
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret-test-key-1234"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert seen["body"]["max_completion_tokens"] == 50 and "max_tokens" not in seen["body"]
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 7, 2)


async def test_openai_compatible_uses_base_url_and_max_tokens():
    seen = {}

    def h(req):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    await OpenAICompatibleAdapter(cfg("openai_compatible", "http://localhost:11434/v1"), transport=mock(h)).chat(REQ)
    assert seen["url"] == "http://localhost:11434/v1/chat/completions" and seen["body"]["max_tokens"] == 50


async def test_anthropic_request_and_usage():
    seen = {}

    def h(req):
        seen["url"], seen["h"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={"id": "msg_1", "content": [{"type": "text", "text": "yo"}],
                                         "stop_reason": "end_turn", "usage": {"input_tokens": 9, "output_tokens": 3}})

    r = await AnthropicAdapter(cfg("anthropic"), transport=mock(h)).chat(REQ)
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["h"]["x-api-key"] == "sk-secret-test-key-1234" and seen["h"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["system"] == "be brief" and seen["body"]["max_tokens"] == 50
    assert all(m["role"] != "system" for m in seen["body"]["messages"])
    assert (r.text, r.input_tokens, r.output_tokens) == ("yo", 9, 3)


async def test_gemini_request_and_usage():
    seen = {}

    def h(req):
        seen["url"], seen["h"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={
            "id": "int_test",
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": "g"}]}],
            "usage": {"total_input_tokens": 4, "total_output_tokens": 1},
        })

    r = await GeminiAdapter(cfg("gemini"), transport=mock(h)).chat(REQ)
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert "key=" not in seen["url"] and seen["h"]["x-goog-api-key"] == "sk-secret-test-key-1234"
    assert seen["body"]["model"] == "m1"
    assert seen["body"]["system_instruction"] == "be brief"
    assert seen["body"]["generation_config"] == {"max_output_tokens": 50}
    assert "temperature" not in seen["body"]["generation_config"]
    assert "top_p" not in seen["body"]["generation_config"]
    assert seen["body"]["store"] is False
    assert seen["body"]["input"] == [{"type": "user_input", "content": [{"type": "text", "text": "hello"}]}]
    assert (r.text, r.input_tokens, r.output_tokens, r.provider_request_id) == ("g", 4, 1, "int_test")


async def test_gemini_interactions_preserve_function_call_history():
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "id": "int_after_tool",
            "status": "completed",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": "done"}]}],
            "usage": {"total_input_tokens": 12, "total_output_tokens": 2},
        })

    request = ChatRequest(
        model="gemini-3.8-flash",
        messages=[
            ChatMessage("user", "What is the weather?"),
            ChatMessage("assistant", "", tool_calls=[
                ToolCall(id="fc_123", name="get_weather", arguments={"city": "Boston"})
            ]),
            ChatMessage("tool", "Sunny", tool_call_id="fc_123", name="get_weather"),
        ],
        system="Be concise",
        tools=[ToolSpec(name="get_weather", description="Get weather", parameters={
            "type": "object", "properties": {"city": {"type": "string"}}
        })],
    )

    result = await GeminiAdapter(cfg("gemini"), transport=mock(h)).chat(request)
    assert seen["body"]["model"] == "gemini-3.8-flash"
    assert seen["body"]["system_instruction"] == "Be concise"
    assert seen["body"]["tools"][0]["type"] == "function"
    assert seen["body"]["input"][1] == {
        "type": "function_call", "id": "fc_123", "name": "get_weather", "arguments": {"city": "Boston"}
    }
    assert seen["body"]["input"][2] == {
        "type": "function_result", "call_id": "fc_123", "name": "get_weather",
        "result": [{"type": "text", "text": "Sunny"}]
    }
    assert result.text == "done"


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limit"), (500, "unavailable"),
                                         (400, "bad_request"), (404, "not_found")])
async def test_error_classification(status, kind):
    t = mock(lambda req: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(ProviderError) as e:
        await OpenAIAdapter(cfg("openai"), transport=t).chat(REQ)
    assert e.value.kind == kind and e.value.message == "nope"


async def test_timeout_and_network_errors():
    def slow(req):
        raise httpx.ReadTimeout("timed out", request=req)

    with pytest.raises(ProviderError) as e:
        await AnthropicAdapter(cfg("anthropic"), transport=mock(slow)).chat(REQ)
    assert e.value.kind == "timeout"

    def down(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(ProviderError) as e:
        await GeminiAdapter(cfg("gemini"), transport=mock(down)).chat(REQ)
    assert e.value.kind == "unavailable"


async def test_provider_key_never_returned_and_encrypted_at_rest(alice, database):
    r = await alice.post("/model-providers", json={"kind": "openai", "name": "OpenAI prod",
                                                   "api_key": "sk-supersecret-abcd1234", "allowed_models": ["gpt-x"]})
    assert r.status_code == 201
    body = r.json()
    assert "supersecret" not in r.text and body["api_key_last4"] == "1234" and body["has_api_key"]
    listed = await alice.get("/model-providers")
    assert "supersecret" not in listed.text and "api_key_enc" not in listed.text
    doc = await database["model_providers"].find_one({"_id": body["id"]})
    assert "supersecret" not in json.dumps(doc, default=str)
    assert doc["api_key_enc"].startswith("gAAAA")  # Fernet token


async def test_connection_test_and_rotation(alice):
    p = (await alice.post("/model-providers", json={"kind": "anthropic", "name": "Claude",
                                                    "api_key": "sk-ant-old-key-0000"})).json()
    seen = []

    def h(req):
        seen.append(req.headers["x-api-key"])
        if req.headers["x-api-key"].endswith("0000"):
            return httpx.Response(401, json={"error": {"type": "authentication_error", "message": "invalid x-api-key"}})
        return httpx.Response(200, json={"data": [{"id": "claude-a"}, {"id": "claude-b"}]})

    registry.test_transport = mock(h)
    try:
        bad = (await alice.post(f"/model-providers/{p['id']}/test")).json()
        assert bad["ok"] is False and "auth" in bad["error"]
        assert (await alice.get(f"/model-providers/{p['id']}")).json()["health"]["status"] == "unhealthy"
        rot = await alice.patch(f"/model-providers/{p['id']}", json={"api_key": "sk-ant-new-key-9999"})
        assert rot.json()["api_key_last4"] == "9999"
        good = (await alice.post(f"/model-providers/{p['id']}/test")).json()
        assert good["ok"] and good["models"] == ["claude-a", "claude-b"]
    finally:
        registry.test_transport = None
    assert seen == ["sk-ant-old-key-0000", "sk-ant-new-key-9999"]
    actions = [i["action"] for i in (await alice.get("/audit-logs")).json()["items"]]
    assert "provider.rotate_key" in actions


async def test_test_model_calls_selected_model_and_records_audit(alice):
    p = (await alice.post("/model-providers", json={"kind": "openai_compatible", "name": "Local model",
                                                    "base_url": "http://localhost:11434/v1"})).json()
    seen = {}

    def h(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "MODEL_OK"}}], "usage": {}})

    registry.test_transport = mock(h)
    try:
        r = await alice.post(f"/model-providers/{p['id']}/test-model", json={"model": "qwen2.5-coder:7b"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True and r.json()["response"] == "MODEL_OK"
        assert seen["url"] == "http://localhost:11434/v1/chat/completions"
        assert seen["body"]["model"] == "qwen2.5-coder:7b"
        assert seen["body"]["messages"][-1]["content"] == "Reply with exactly: MODEL_OK"
    finally:
        registry.test_transport = None

    actions = [i["action"] for i in (await alice.get("/audit-logs")).json()["items"]]
    assert "provider.test_model" in actions

async def test_test_model_timeout_is_bounded_and_returned_as_json(alice):
    p = (await alice.post("/model-providers", json={
        "kind": "openai_compatible",
        "name": "Slow local model",
        "base_url": "http://localhost:11434/v1",
        "timeout_seconds": 60,
    })).json()
    seen = {}

    def h(req):
        seen["timeout"] = req.extensions.get("timeout", {})
        raise httpx.ReadTimeout("simulated provider stall", request=req)

    registry.test_transport = mock(h)
    try:
        response = await alice.post(f"/model-providers/{p['id']}/test-model", json={"model": "slow-model"})
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is False
        assert response.json()["error"].startswith("timeout:")
        assert seen["timeout"].get("read", 60) <= 20
    finally:
        registry.test_transport = None


async def test_gemini_model_catalog_excludes_legacy_models():
    def h(req):
        assert req.url.path.endswith("/models")
        return httpx.Response(200, json={"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.8-image", "supportedGenerationMethods": ["predict"]},
        ]})

    models = await GeminiAdapter(cfg("gemini"), transport=mock(h)).list_models()
    assert models == ["gemini-3.8-flash"]


async def test_provider_validation(alice):
    assert (await alice.post("/model-providers", json={"kind": "openai", "name": "nokey"})).status_code == 422
    assert (await alice.post("/model-providers", json={"kind": "openai_compatible", "name": "nourl"})).status_code == 422
    assert (await alice.post("/model-providers", json={"kind": "demo", "name": "d2"})).status_code == 409
