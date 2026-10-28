"""Adapter wire formats (offline via httpx.MockTransport) and credential handling."""
import json

import httpx
import pytest

from app.providers import registry
from app.providers.anthropic import AnthropicAdapter
from app.providers.base import ChatMessage, ChatRequest, ProviderConfig, ProviderError
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
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "g"}]}, "finishReason": "STOP"}],
                                         "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1}})

    r = await GeminiAdapter(cfg("gemini"), transport=mock(h)).chat(REQ)
    assert seen["url"] == "https://generativelanguage.googleapis.com/v1beta/models/m1:generateContent"
    assert "key=" not in seen["url"] and seen["h"]["x-goog-api-key"] == "sk-secret-test-key-1234"
    assert seen["body"]["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    assert seen["body"]["generationConfig"]["maxOutputTokens"] == 50
    assert (r.text, r.input_tokens, r.output_tokens) == ("g", 4, 1)


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


async def test_provider_validation(alice):
    assert (await alice.post("/model-providers", json={"kind": "openai", "name": "nokey"})).status_code == 422
    assert (await alice.post("/model-providers", json={"kind": "openai_compatible", "name": "nourl"})).status_code == 422
    assert (await alice.post("/model-providers", json={"kind": "demo", "name": "d2"})).status_code == 409
