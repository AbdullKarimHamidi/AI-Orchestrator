import time

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.exceptions import Conflict, NotFound
from app.core.ids import new_id
from app.core.security import get_cipher
from app.providers.base import ProviderConfig, ProviderError
from app.providers.demo import DEMO_MODELS
from app.providers.registry import build_adapter
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.providers import ProviderRepository
from app.schemas.providers import ProviderCreate, ProviderUpdate

DEMO_PROVIDER_NAME = "Demo (synthetic, no real model)"


def present(p: dict) -> dict:
    """Public representation. Never includes the encrypted or plaintext key."""
    return {"id": p["_id"], "kind": p["kind"], "name": p["name"], "base_url": p.get("base_url"),
            "has_api_key": bool(p.get("api_key_enc")), "api_key_last4": p.get("api_key_last4"),
            "allowed_models": p.get("allowed_models", []), "timeout_seconds": p.get("timeout_seconds", 60),
            "enabled": p.get("enabled", True), "pricing": p.get("pricing", {}),
            "health": p.get("health") or {"status": "unknown"}, "created_at": p["created_at"],
            "updated_at": p.get("updated_at", p["created_at"])}


def runtime_config(p: dict) -> ProviderConfig:
    key = get_cipher().decrypt(p["api_key_enc"]) if p.get("api_key_enc") else None
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

    async def list(self, ws_id: str) -> list[dict]:
        await self.ensure_demo(ws_id)
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
