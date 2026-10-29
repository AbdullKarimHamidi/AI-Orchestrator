import logging
import time

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.core.security import get_cipher
from app.providers.base import ChatMessage, ChatRequest, ProviderConfig, ProviderError
from app.providers.demo import DEMO_MODELS
from app.providers.presets import FREE_PRESETS, PRESETS_BY_ID, Preset
from app.providers.registry import build_adapter
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.providers import ProviderRepository
from app.schemas.providers import ProviderCreate, ProviderUpdate

log = logging.getLogger(__name__)

DEMO_PROVIDER_NAME = "Demo (synthetic, no real model)"


def _env_key(p: dict) -> str:
    """Key for providers set up from an environment variable (read at call time, never stored)."""
    return getattr(get_settings(), p["key_from_env"], "") if p.get("key_from_env") else ""


def present(p: dict) -> dict:
    """Public representation. Never includes the encrypted or plaintext key."""
    env_key = "" if p.get("api_key_enc") else _env_key(p)
    return {"id": p["_id"], "kind": p["kind"], "name": p["name"], "base_url": p.get("base_url"),
            "has_api_key": bool(p.get("api_key_enc") or env_key),
            "api_key_last4": p.get("api_key_last4") or (env_key[-4:] if env_key else None),
            "preset": p.get("preset"), "suggested_models": p.get("suggested_models", []),
            "allowed_models": p.get("allowed_models", []), "timeout_seconds": p.get("timeout_seconds", 60),
            "enabled": p.get("enabled", True), "pricing": p.get("pricing", {}),
            "health": p.get("health") or {"status": "unknown"}, "created_at": p["created_at"],
            "updated_at": p.get("updated_at", p["created_at"])}


def runtime_config(p: dict) -> ProviderConfig:
    key = get_cipher().decrypt(p["api_key_enc"]) if p.get("api_key_enc") else (_env_key(p) or None)
    return ProviderConfig(kind=p["kind"], api_key=key, base_url=p.get("base_url"),
                          timeout_seconds=float(p.get("timeout_seconds", 60)))


class ProviderService:
    def __init__(self, db: AsyncDatabase):
        self.repo = ProviderRepository(db)
        self.audit = AuditRepository(db)

    async def ensure_demo(self, ws_id: str) -> None:
        if not get_settings().demo_mode or await self.repo.by_kind(ws_id, "demo"):
            return
        t = now()
        try:
            await self.repo.insert({"_id": new_id("prv"), "workspace_id": ws_id, "kind": "demo",
                                    "name": DEMO_PROVIDER_NAME, "allowed_models": list(DEMO_MODELS),
                                    "timeout_seconds": 120, "enabled": True, "pricing": {},
                                    "health": {"status": "healthy", "checked_at": t}, "created_at": t,
                                    "updated_at": t})
        except DuplicateKeyError:
            pass

    async def ensure_presets(self, ws_id: str) -> None:
        """Adds every free preset whose key (or Ollama URL) is set in the environment. The key stays
        in the environment: the provider references it, so rotating the .env value just works."""
        s = get_settings()
        for preset in FREE_PRESETS:
            value = getattr(s, preset.env_key, "")
            if not value or await self.repo.by_preset(ws_id, preset.id):
                continue
            base_url = value.rstrip("/") if not preset.needs_key else preset.base_url
            try:
                await self.repo.insert(self._preset_doc(ws_id, preset, base_url) | (
                    {"key_from_env": preset.env_key} if preset.needs_key else {}))
            except DuplicateKeyError:
                pass  # concurrent request, or the user already has a provider with this name

    @staticmethod
    def _preset_doc(ws_id: str, preset: Preset, base_url: str | None) -> dict:
        t = now()
        return {"_id": new_id("prv"), "workspace_id": ws_id, "kind": preset.kind, "name": preset.name,
                "base_url": base_url, "preset": preset.id, "suggested_models": list(preset.models),
                "allowed_models": [], "timeout_seconds": preset.timeout_seconds, "enabled": True, "pricing": {},
                "health": {"status": "unknown"}, "created_at": t, "updated_at": t}

    async def presets(self, ws_id: str) -> list[dict]:
        """The free-provider catalog, with the workspace's provider for each one when it exists."""
        s = get_settings()
        out = []
        for preset in FREE_PRESETS:
            existing = await self.repo.by_preset(ws_id, preset.id)
            out.append({"id": preset.id, "name": preset.name, "kind": preset.kind, "base_url": preset.base_url,
                        "models": list(preset.models), "signup_url": preset.signup_url,
                        "free_tier": preset.free_tier, "needs_key": preset.needs_key,
                        "env_var": preset.env_key.upper(), "env_configured": bool(getattr(s, preset.env_key, "")),
                        "provider_id": existing["_id"] if existing else None})
        return out

    async def add_preset(self, ws_id: str, user_id: str, preset_id: str, api_key: str | None,
                         base_url: str | None) -> dict:
        preset = PRESETS_BY_ID.get(preset_id)
        if preset is None:
            raise NotFound("Unknown free provider")
        if await self.repo.by_preset(ws_id, preset_id):
            raise Conflict(f"{preset.name} is already set up in this workspace", code="PRESET_EXISTS")
        if preset.needs_key and not api_key:
            raise Unprocessable(f"Paste your {preset.name} API key (get one at {preset.signup_url})",
                                code="API_KEY_REQUIRED")
        doc = self._preset_doc(ws_id, preset, (base_url or preset.base_url or "").rstrip("/") or None)
        if api_key:
            doc |= {"api_key_enc": get_cipher().encrypt(api_key), "api_key_last4": api_key[-4:],
                    "key_rotated_at": now()}
        try:
            await self.repo.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A provider with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "provider.create", "provider", doc["_id"],
                                {"kind": preset.kind, "preset": preset.id})
        return doc

    async def list(self, ws_id: str) -> list[dict]:
        await self.ensure_demo(ws_id)
        await self.ensure_presets(ws_id)
        items, _ = await self.repo.list(ws_id, sort=[("created_at", 1)], limit=200)
        return items

    async def get(self, ws_id: str, pid: str) -> dict:
        p = await self.repo.get(ws_id, pid)
        if not p:
            raise NotFound("Provider not found")
        return p

    async def create(self, ws_id: str, user_id: str, req: ProviderCreate) -> dict:
        if req.kind == "demo":
            raise Conflict("The demo provider is managed automatically", code="DEMO_MANAGED")
        t = now()
        doc = {"_id": new_id("prv"), "workspace_id": ws_id, "kind": req.kind, "name": req.name,
               "base_url": str(req.base_url).rstrip("/") if req.base_url else None,
               "allowed_models": req.allowed_models, "timeout_seconds": req.timeout_seconds, "enabled": True,
               "pricing": {k: v.model_dump() for k, v in req.pricing.items()},
               "health": {"status": "unknown"}, "created_at": t, "updated_at": t}
        if req.api_key:
            doc |= {"api_key_enc": get_cipher().encrypt(req.api_key), "api_key_last4": req.api_key[-4:],
                    "key_rotated_at": t}
        try:
            await self.repo.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A provider with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "provider.create", "provider", doc["_id"], {"kind": req.kind})
        return doc

    async def update(self, ws_id: str, user_id: str, pid: str, req: ProviderUpdate) -> dict:
        p = await self.get(ws_id, pid)
        fields = req.model_dump(exclude_unset=True, exclude={"api_key"}, mode="json")
        if "base_url" in fields and fields["base_url"]:
            fields["base_url"] = fields["base_url"].rstrip("/")
        if req.api_key:
            if p["kind"] == "demo":
                raise Conflict("The demo provider has no key", code="DEMO_MANAGED")
            fields |= {"api_key_enc": get_cipher().encrypt(req.api_key), "api_key_last4": req.api_key[-4:],
                       "key_rotated_at": now(), "health": {"status": "unknown"}}
        try:
            updated = await self.repo.update(ws_id, pid, fields)
        except DuplicateKeyError as exc:
            raise Conflict("A provider with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "provider.rotate_key" if req.api_key else "provider.update",
                                "provider", pid, {"fields": sorted(fields)})
        return updated  # type: ignore[return-value]

    async def delete(self, ws_id: str, user_id: str, pid: str) -> None:
        p = await self.get(ws_id, pid)
        if p["kind"] == "demo":
            raise Conflict("The demo provider is managed automatically", code="DEMO_MANAGED")
        await self.repo.delete(ws_id, pid)
        await self.audit.record(ws_id, user_id, "provider.delete", "provider", pid)

    async def test_model(self, ws_id: str, user_id: str, pid: str, model: str) -> dict:
        """Make one tiny real inference request to verify this exact provider/model pair."""
        p = await self.get(ws_id, pid)
        model = model.strip()
        if not model:
            raise Unprocessable("Enter a model ID to test", code="MODEL_REQUIRED")
        if not p.get("enabled", True):
            raise Unprocessable("This provider is disabled. Enable it before testing.", code="PROVIDER_DISABLED")
        if p.get("allowed_models") and model not in p["allowed_models"]:
            raise Unprocessable(f"Model {model} is not on the allowlist for this provider", code="MODEL_NOT_ALLOWED")
        started = time.monotonic()
        try:
            # This is a synchronous UI probe, not an agent run. Keep it below
            # reverse-proxy/browser timeouts so provider stalls return a JSON result
            # instead of a proxy-generated HTML 500.
            cfg = runtime_config(p)
            cfg.timeout_seconds = min(cfg.timeout_seconds, 20.0)
            result = await build_adapter(cfg).chat(ChatRequest(
                model=model,
                system="You are checking whether this model is available. Follow the user instruction exactly.",
                messages=[ChatMessage(role="user", content="Reply with exactly: MODEL_OK")],
                max_output_tokens=16,
                temperature=0,
            ))
            response = (result.text or "").strip()[:300]
            if not response and not result.tool_calls:
                raise ProviderError("unknown", "The model returned an empty response")
            outcome = {"ok": True, "response": response or "Model responded (tool call)", "error": None}
        except ProviderError as exc:
            outcome = {"ok": False, "response": None, "error": f"{exc.kind}: {exc.message}"[:500]}
        except ValueError as exc:
            outcome = {"ok": False, "response": None, "error": str(exc)[:500]}
        except Exception as exc:
            # Do not expose request headers, credentials, or provider internals in API errors.
            outcome = {"ok": False, "response": None, "error": f"Unexpected provider error ({type(exc).__name__})"}
        latency = int((time.monotonic() - started) * 1000)
        try:
            await self.audit.record(ws_id, user_id, "provider.test_model", "provider", pid,
                                    {"model": model, "ok": outcome["ok"], "latency_ms": latency})
        except Exception:
            # The probe result should still reach the user if the audit collection
            # has a transient failure. Keep the failure visible in sanitized logs.
            log.exception("failed to audit provider model test",
                          extra={"extra_fields": {"provider_id": pid, "model": model, "ok": outcome["ok"]}})
        return {**outcome, "latency_ms": latency}

    async def test_connection(self, ws_id: str, user_id: str, pid: str) -> dict:
        p = await self.get(ws_id, pid)
        started = time.monotonic()
        try:
            models = await build_adapter(runtime_config(p)).list_models()
            result = {"ok": True, "models": models[:500], "error": None}
        except ProviderError as exc:
            result = {"ok": False, "models": [], "error": f"{exc.kind}: {exc.message}"}
        except ValueError as exc:  # undecryptable key
            result = {"ok": False, "models": [], "error": str(exc)}
        latency = int((time.monotonic() - started) * 1000)
        await self.repo.update(ws_id, pid, {"health": {"status": "healthy" if result["ok"] else "unhealthy",
                                                       "checked_at": now(), "latency_ms": latency,
                                                       "error": result["error"]}})
        await self.audit.record(ws_id, user_id, "provider.test", "provider", pid, {"ok": result["ok"]})
        return {**result, "latency_ms": latency}
