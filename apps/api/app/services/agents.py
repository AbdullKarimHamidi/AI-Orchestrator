"""Agent lifecycle and versioning.

Invariants:
- The draft is the only mutable configuration. Published versions are immutable
  snapshots in agent_versions (append-only; config_hash is a SHA-256 of canonical JSON).
- Runs of a published agent execute the exact config of `published_version`, so editing
  the draft never changes behavior of what is published.
- Status machine: draft -> published <-> paused; any -> retired (terminal).
"""
import hashlib
import json

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.repositories.agents import AgentRepository, AgentVersionRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.providers import ProviderRepository
from app.repositories.tools import ToolRepository
from app.schemas.agents import AgentConfig, AgentCreate, AgentUpdate


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def flatten(d: object, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        out[prefix] = d
    return out


def diff_configs(a: dict, b: dict) -> list[dict]:
    fa, fb = flatten(a), flatten(b)
    changes = []
    for key in sorted(set(fa) | set(fb)):
        if fa.get(key) != fb.get(key):
            changes.append({"path": key, "from": fa.get(key), "to": fb.get(key)})
    return changes


class AgentService:
    def __init__(self, db: AsyncDatabase):
        self.agents = AgentRepository(db)
        self.versions = AgentVersionRepository(db)
        self.providers = ProviderRepository(db)
        self.tools = ToolRepository(db)
        self.kbs = KnowledgeBaseRepository(db)
        self.audit = AuditRepository(db)

    async def present(self, ws_id: str, a: dict) -> dict:
        latest = await self.versions.latest(ws_id, a["_id"])
        dirty = latest is None or latest["config_hash"] != config_hash(a["draft"])
        return {**a, "id": a["_id"], "latest_version": latest["version"] if latest else None, "draft_dirty": dirty}

    async def get(self, ws_id: str, agent_id: str) -> dict:
        a = await self.agents.get(ws_id, agent_id)
        if not a:
            raise NotFound("Agent not found")
        return a

    async def create(self, ws_id: str, user_id: str, req: AgentCreate) -> dict:
        t = now()
        doc = {"_id": new_id("agt"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "description": req.description, "status": "draft",
               "draft": req.config.model_dump(mode="json"), "revision": 1, "published_version": None,
               "created_by": user_id, "created_at": t, "updated_at": t, "deleted": False}
        try:
            await self.agents.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("An agent with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "agent.create", "agent", doc["_id"])
        return doc

    async def update(self, ws_id: str, user_id: str, agent_id: str, req: AgentUpdate) -> dict:
        a = await self.get(ws_id, agent_id)
        if a["status"] == "retired":
            raise Conflict("Retired agents cannot be edited", code="AGENT_RETIRED")
        fields: dict = {}
        if req.name is not None:
            fields |= {"name": req.name, "name_lower": req.name.lower()}
        if req.description is not None:
            fields["description"] = req.description
        if req.config is not None:
            fields["draft"] = req.config.model_dump(mode="json")
        try:
            updated = await self.agents.update_if_revision(ws_id, agent_id, req.revision, fields)
        except DuplicateKeyError as exc:
            raise Conflict("An agent with this name already exists", code="NAME_TAKEN") from exc
        if updated is None:
            raise Conflict("Agent was modified by someone else. Reload and retry.", code="REVISION_MISMATCH",
                           details={"current_revision": a["revision"]})
        await self.audit.record(ws_id, user_id, "agent.update", "agent", agent_id, {"fields": sorted(fields)})
        return updated

    async def delete(self, ws_id: str, user_id: str, agent_id: str) -> None:
        await self.get(ws_id, agent_id)
        # Soft delete keeps versions and run history reproducible and auditable.
        await self.agents.update(ws_id, agent_id, {"deleted": True, "status": "retired",
                                                   "name_lower": f"{agent_id}:deleted"})
        await self.audit.record(ws_id, user_id, "agent.delete", "agent", agent_id)

    async def clone(self, ws_id: str, user_id: str, agent_id: str, name: str) -> dict:
        src = await self.get(ws_id, agent_id)
        return await self.create(ws_id, user_id, AgentCreate(name=name, description=src["description"],
                                                             config=AgentConfig.model_validate(src["draft"])))

    async def _validate_publishable(self, ws_id: str, cfg: dict) -> None:
        refs = ([cfg["model"]] if cfg.get("model") else []) + list(cfg.get("fallbacks") or [])
        if not cfg.get("model"):
            raise Unprocessable("A primary model is required before publishing", code="MODEL_REQUIRED")
        for ref in refs:
            p = await self.providers.get(ws_id, ref["provider_id"])
            if not p:
                raise Unprocessable(f"Provider {ref['provider_id']} does not exist in this workspace",
                                    code="PROVIDER_NOT_FOUND")
            if p.get("allowed_models") and ref["model"] not in p["allowed_models"]:
                raise Unprocessable(f"Model {ref['model']} is not on the allowlist of provider {p['name']}",
                                    code="MODEL_NOT_ALLOWED")
        tool_ids = list(cfg.get("tool_ids") or [])
        found = {t["_id"] for t in await self.tools.many(ws_id, tool_ids)}
        if missing := [t for t in tool_ids if t not in found]:
            raise Unprocessable(f"Tools not found in this workspace: {', '.join(missing)}", code="TOOL_NOT_FOUND")
        kb_ids = list(cfg.get("knowledge_base_ids") or [])
        found = {k["_id"] for k in await self.kbs.many(ws_id, kb_ids)}
        if missing := [k for k in kb_ids if k not in found]:
            raise Unprocessable(f"Knowledge bases not found: {', '.join(missing)}", code="KNOWLEDGE_BASE_NOT_FOUND")

    async def publish(self, ws_id: str, user_id: str, agent_id: str, note: str) -> dict:
        a = await self.get(ws_id, agent_id)
        if a["status"] == "retired":
            raise Conflict("Retired agents cannot be published", code="AGENT_RETIRED")
        await self._validate_publishable(ws_id, a["draft"])
        h = config_hash(a["draft"])
        latest = await self.versions.latest(ws_id, agent_id)
        if latest and latest["config_hash"] == h and a.get("published_version") == latest["version"]:
            raise Conflict(f"No changes since version {latest['version']}", code="NO_CHANGES")
        number = (latest["version"] if latest else 0) + 1
        try:
            await self.versions.insert({"_id": new_id("agv"), "workspace_id": ws_id, "agent_id": agent_id,
                                        "version": number, "config": a["draft"], "config_hash": h, "note": note,
                                        "created_by": user_id, "created_at": now()})
        except DuplicateKeyError as exc:  # concurrent publish
            raise Conflict("Another publish happened concurrently; retry", code="CONCURRENT_PUBLISH") from exc
        updated = await self.agents.update(ws_id, agent_id, {"status": "published", "published_version": number})
        await self.audit.record(ws_id, user_id, "agent.publish", "agent", agent_id, {"version": number})
        return updated  # type: ignore[return-value]

    async def transition(self, ws_id: str, user_id: str, agent_id: str, action: str) -> dict:
        a = await self.get(ws_id, agent_id)
        allowed = {"pause": ({"published"}, "paused"), "resume": ({"paused"}, "published"),
                   "retire": ({"draft", "published", "paused"}, "retired")}
        sources, target = allowed[action]
        if a["status"] not in sources:
            raise Conflict(f"Cannot {action} an agent in status '{a['status']}'", code="INVALID_TRANSITION")
        updated = await self.agents.update(ws_id, agent_id, {"status": target})
        await self.audit.record(ws_id, user_id, f"agent.{action}", "agent", agent_id)
        return updated  # type: ignore[return-value]

    async def rollback(self, ws_id: str, user_id: str, agent_id: str, version: int) -> dict:
        """Points the published pointer at an existing immutable version and resets the draft
        to that config. No version is rewritten."""
        a = await self.get(ws_id, agent_id)
        if a["status"] == "retired":
            raise Conflict("Retired agents cannot be rolled back", code="AGENT_RETIRED")
        v = await self.versions.by_number(ws_id, agent_id, version)
        if not v:
            raise NotFound(f"Version {version} not found")
        status = "paused" if a["status"] == "paused" else "published"
        updated = await self.agents.update(ws_id, agent_id, {"published_version": version, "draft": v["config"],
                                                             "status": status})
        await self.audit.record(ws_id, user_id, "agent.rollback", "agent", agent_id,
                                {"from": a.get("published_version"), "to": version})
        return updated  # type: ignore[return-value]

    async def list_versions(self, ws_id: str, agent_id: str) -> list[dict]:
        await self.get(ws_id, agent_id)
        return await self.versions.for_agent(ws_id, agent_id)

    async def compare(self, ws_id: str, agent_id: str, a_v: int, b_v: int) -> list[dict]:
        va = await self.versions.by_number(ws_id, agent_id, a_v)
        vb = await self.versions.by_number(ws_id, agent_id, b_v)
        if not va or not vb:
            raise NotFound("Version not found")
        return diff_configs(va["config"], vb["config"])
