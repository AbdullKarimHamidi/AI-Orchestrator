"""Free provider presets and the starter agent pack."""
from app.core.config import get_settings
from app.providers.presets import FREE_PRESETS
from app.services.providers import runtime_config
from tests.conftest import make_user


async def test_preset_catalog_lists_every_free_provider():
    alice = await make_user("presets")
    r = await alice.get("/model-providers/presets")
    assert r.status_code == 200
    items = {p["id"]: p for p in r.json()}
    assert set(items) == {p.id for p in FREE_PRESETS}
    assert items["groq"]["signup_url"].startswith("https://") and items["groq"]["provider_id"] is None
    assert items["gemini"]["models"][0] == "gemini-3.8-flash"
    assert "gemini-2.5-flash" not in items["gemini"]["models"]
    assert items["ollama"]["needs_key"] is False
    assert items["ollama"]["base_url"] == "http://host.docker.internal:11434/v1"
    assert "qwen2.5-coder:7b" in items["ollama"]["models"]


async def test_add_preset_needs_key_and_stores_it_encrypted():
    alice = await make_user("addpreset")
    r = await alice.post("/model-providers/presets/groq", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "API_KEY_REQUIRED"
    r = await alice.post("/model-providers/presets/groq", json={"api_key": "gsk_test_key_abcd"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["kind"], p["preset"], p["api_key_last4"]) == ("openai_compatible", "groq", "abcd")
    assert p["base_url"] == "https://api.groq.com/openai/v1"
    assert p["allowed_models"] == [] and p["suggested_models"][0] == "llama-3.3-70b-versatile"
    assert (await alice.post("/model-providers/presets/groq", json={"api_key": "x"})).status_code == 409
    assert (await alice.post("/model-providers/presets/nope", json={"api_key": "x"})).status_code == 404
    catalog = {x["id"]: x for x in (await alice.get("/model-providers/presets")).json()}
    assert catalog["groq"]["provider_id"] == p["id"]


async def test_env_keys_provision_providers_without_storing_the_key(database):
    s = get_settings()
    s.gemini_api_key, s.ollama_base_url = "AIza-env-key-wxyz", "http://localhost:11434/v1/"
    try:
        alice = await make_user("envkeys")
        providers = {p["preset"]: p for p in (await alice.get("/model-providers")).json() if p["preset"]}
        assert set(providers) == {"gemini", "ollama"}
        assert providers["gemini"]["has_api_key"] and providers["gemini"]["api_key_last4"] == "wxyz"
        assert providers["ollama"]["base_url"] == "http://localhost:11434/v1"
        doc = await database["model_providers"].find_one({"_id": providers["gemini"]["id"]})
        assert "api_key_enc" not in doc and runtime_config(doc).api_key == "AIza-env-key-wxyz"
    finally:
        s.gemini_api_key = s.ollama_base_url = ""


async def test_starter_pack_runs_on_demo_then_moves_to_free_provider():
    s = get_settings()
    s.seed_starter_agents = True
    try:
        alice = await make_user("starter")
    finally:
        s.seed_starter_agents = False
    agents = (await alice.get("/agents", params={"limit": 50})).json()["items"]
    assert len(agents) >= 8 and all(a["status"] == "published" for a in agents)
    assert {a["draft"]["model"]["model"] for a in agents} == {"demo-echo"}

    groq = (await alice.post("/model-providers/presets/groq", json={"api_key": "gsk_test_key_abcd"})).json()
    gemini = (await alice.post("/model-providers/presets/gemini", json={"api_key": "AIza-test-key"})).json()
    coder = next(a for a in agents if a["name"] == "Code Helper")
    edited = (await alice.patch(f"/agents/{coder['id']}", json={
        "revision": coder["revision"], "config": coder["draft"] | {"system_prompt": "my own prompt"}})).json()

    r = await alice.post("/agents/starter-pack")
    assert r.status_code == 200, r.text
    assert "Code Helper" in r.json()["skipped"] and "General Assistant" in r.json()["updated"]
    after = {a["name"]: a for a in (await alice.get("/agents", params={"limit": 50})).json()["items"]}
    gen = after["General Assistant"]
    assert gen["draft"]["model"] == {"provider_id": groq["id"], "model": "llama-3.3-70b-versatile"}
    assert gen["draft"]["fallbacks"][0]["provider_id"] == gemini["id"]
    assert gen["published_version"] == 2 and not gen["draft_dirty"]
    assert after["Code Helper"]["draft"]["system_prompt"] == "my own prompt" == edited["draft"]["system_prompt"]
