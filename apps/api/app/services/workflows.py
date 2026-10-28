"""Workflow lifecycle, versioning and run creation.

Mirrors agents: the draft definition is the only mutable copy; publishing appends an immutable
version; production runs execute the published version. Runs are ordinary documents in the
``runs`` queue with ``kind="workflow"``, so the existing worker, leases, cancellation,
timeouts, SSE events and the run inspector all apply unchanged.
"""
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound, Unprocessable
from app.core.ids import new_id
from app.repositories.agents import AgentRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.knowledge import KnowledgeBaseRepository
from app.repositories.runs import RunEventRepository, RunRepository
from app.repositories.tools import ToolRepository
from app.repositories.workflows import WorkflowRepository, WorkflowVersionRepository
from app.schemas.workflows import WorkflowCreate, WorkflowRunCreate, WorkflowUpdate
from app.services.agents import config_hash
from app.services.rbac import has_permission
from app.services.runs import MAX_ATTEMPTS, RunService


class WorkflowService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.workflows = WorkflowRepository(db)
        self.versions = WorkflowVersionRepository(db)
        self.agents = AgentRepository(db)
        self.tools = ToolRepository(db)
        self.kbs = KnowledgeBaseRepository(db)
        self.runs = RunRepository(db)
        self.events = RunEventRepository(db)
        self.audit = AuditRepository(db)

    async def present(self, ws_id: str, w: dict) -> dict:
        latest = await self.versions.latest(ws_id, w["_id"])
        dirty = latest is None or latest["definition_hash"] != config_hash(w["draft"])
        return {**w, "id": w["_id"], "latest_version": latest["version"] if latest else None, "draft_dirty": dirty}

    async def get(self, ws_id: str, workflow_id: str) -> dict:
        w = await self.workflows.get(ws_id, workflow_id)
        if not w:
            raise NotFound("Workflow not found")
        return w

    async def create(self, ws_id: str, user_id: str, req: WorkflowCreate) -> dict:
        t = now()
        doc = {"_id": new_id("wfl"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "description": req.description, "status": "draft",
               "draft": req.definition.model_dump(mode="json"), "revision": 1, "published_version": None,
               "created_by": user_id, "created_at": t, "updated_at": t, "deleted": False}
        try:
            await self.workflows.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A workflow with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "workflow.create", "workflow", doc["_id"])
        return doc

    async def update(self, ws_id: str, user_id: str, workflow_id: str, req: WorkflowUpdate) -> dict:
        w = await self.get(ws_id, workflow_id)
        if w["status"] == "archived":
            raise Conflict("Archived workflows cannot be edited", code="WORKFLOW_ARCHIVED")
        fields: dict = {}
        if req.name is not None:
            fields |= {"name": req.name, "name_lower": req.name.lower()}
        if req.description is not None:
            fields["description"] = req.description
        if req.definition is not None:
            fields["draft"] = req.definition.model_dump(mode="json")
        try:
            updated = await self.workflows.update_if_revision(ws_id, workflow_id, req.revision, fields)
        except DuplicateKeyError as exc:
            raise Conflict("A workflow with this name already exists", code="NAME_TAKEN") from exc
        if updated is None:
            raise Conflict("Workflow was modified by someone else. Reload and retry.", code="REVISION_MISMATCH",
                           details={"current_revision": w["revision"]})
        await self.audit.record(ws_id, user_id, "workflow.update", "workflow", workflow_id,
                                {"fields": sorted(fields)})
        return updated

    async def delete(self, ws_id: str, user_id: str, workflow_id: str) -> None:
        await self.get(ws_id, workflow_id)
        await self.workflows.update(ws_id, workflow_id, {"deleted": True, "status": "archived",
                                                         "name_lower": f"{workflow_id}:deleted"})
        await self.audit.record(ws_id, user_id, "workflow.delete", "workflow", workflow_id)

    async def validate_references(self, ws_id: str, definition: dict) -> list[str]:
        """Problems that schema validation cannot see: references to agents, tools and
        knowledge bases in this workspace. Returns human-readable messages (empty = valid)."""
        problems: list[str] = []
        steps = definition.get("steps") or []
        if not steps:
            problems.append("The workflow has no steps")
        for s in steps:
            if s["type"] == "agent":
                a = await self.agents.get(ws_id, s.get("agent_id") or "")
                if not a:
                    problems.append(f"Step '{s['id']}': agent {s.get('agent_id')} not found")
                elif a["status"] != "published" or not a.get("published_version"):
                    problems.append(f"Step '{s['id']}': agent '{a['name']}' is {a['status']}; publish it first")
            elif s["type"] == "tool":
                if not await self.tools.many(ws_id, [s.get("tool_id") or ""]):
                    problems.append(f"Step '{s['id']}': tool {s.get('tool_id')} not found")
            elif s["type"] == "knowledge":
                ids = list(s.get("knowledge_base_ids") or [])
                found = {k["_id"] for k in await self.kbs.many(ws_id, ids)}
                if missing := [k for k in ids if k not in found]:
                    problems.append(f"Step '{s['id']}': knowledge bases not found: {', '.join(missing)}")
        return problems

    async def publish(self, ws_id: str, user_id: str, workflow_id: str, note: str) -> dict:
        w = await self.get(ws_id, workflow_id)
        if w["status"] == "archived":
            raise Conflict("Archived workflows cannot be published", code="WORKFLOW_ARCHIVED")
        if problems := await self.validate_references(ws_id, w["draft"]):
            raise Unprocessable("; ".join(problems), code="WORKFLOW_INVALID", details={"problems": problems})
        h = config_hash(w["draft"])
        latest = await self.versions.latest(ws_id, workflow_id)
        if latest and latest["definition_hash"] == h and w.get("published_version") == latest["version"]:
            raise Conflict(f"No changes since version {latest['version']}", code="NO_CHANGES")
        number = (latest["version"] if latest else 0) + 1
        try:
            await self.versions.insert({"_id": new_id("wfv"), "workspace_id": ws_id, "workflow_id": workflow_id,
                                        "version": number, "definition": w["draft"], "definition_hash": h,
                                        "note": note, "created_by": user_id, "created_at": now()})
        except DuplicateKeyError as exc:
            raise Conflict("Another publish happened concurrently; retry", code="CONCURRENT_PUBLISH") from exc
        updated = await self.workflows.update(ws_id, workflow_id, {"status": "published", "published_version": number})
        await self.audit.record(ws_id, user_id, "workflow.publish", "workflow", workflow_id, {"version": number})
        return updated  # type: ignore[return-value]

    async def set_archived(self, ws_id: str, user_id: str, workflow_id: str, archived: bool) -> dict:
        w = await self.get(ws_id, workflow_id)
        status = "archived" if archived else ("published" if w.get("published_version") else "draft")
        updated = await self.workflows.update(ws_id, workflow_id, {"status": status})
        await self.audit.record(ws_id, user_id, "workflow.archive" if archived else "workflow.restore",
                                "workflow", workflow_id)
        return updated  # type: ignore[return-value]

    async def list_versions(self, ws_id: str, workflow_id: str) -> list[dict]:
        await self.get(ws_id, workflow_id)
        return await self.versions.for_workflow(ws_id, workflow_id)

    async def create_run(self, ws_id: str, user_id: str, role: str, workflow_id: str, req: WorkflowRunCreate,
                         idempotency_key: str | None) -> tuple[dict, bool]:
        w = await self.get(ws_id, workflow_id)
        if w["status"] == "archived":
            raise Conflict("Archived workflows cannot run", code="WORKFLOW_ARCHIVED")
        if req.source == "draft":
            if not has_permission(role, "agents:write"):
                raise Forbidden("Testing a draft requires the agents:write permission")
            definition, version = w["draft"], None
        else:
            if not w.get("published_version"):
                raise Conflict("Workflow is not published", code="WORKFLOW_NOT_RUNNABLE")
            v = await self.versions.by_number(ws_id, workflow_id, w["published_version"])
            if not v:
                raise Conflict("Published version is missing", code="VERSION_MISSING")
            definition, version = v["definition"], v["version"]
        msg = req.input.get("message")
        if not isinstance(msg, str) or not msg.strip():
            raise Unprocessable("input.message must be a non-empty string", code="INVALID_INPUT")
        if len(msg) > 100_000:
            raise Unprocessable("input.message is too long", code="INVALID_INPUT")
        if problems := await self.validate_references(ws_id, definition):
            raise Unprocessable("; ".join(problems), code="WORKFLOW_INVALID", details={"problems": problems})
        await RunService(self.db).check_spend(ws_id)

        s = get_settings()
        timeout = min(req.timeout_seconds or s.default_run_timeout_seconds * 2, s.max_run_timeout_seconds)
        t = now()
        doc = {"_id": new_id("run"), "workspace_id": ws_id, "kind": "workflow", "agent_id": "",
               "agent_name": w["name"], "agent_version": version, "workflow_id": w["_id"],
               "workflow_name": w["name"], "workflow_version": version, "source": req.source,
               "config": definition, "input": req.input, "status": "queued", "demo": False, "output": None,
               "error": None, "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
               "attempt": 0, "max_attempts": MAX_ATTEMPTS, "cancel_requested": False, "timeout_seconds": timeout,
               "deadline_at": None, "available_at": t, "lease_owner": None, "lease_expires_at": None,
               "event_seq": 0, "created_by": user_id, "created_at": t, "updated_at": t}
        if idempotency_key:
            doc["idempotency_key"] = idempotency_key
            run, created = await self.runs.insert_idempotent(doc)
        else:
            run, created = await self.runs.insert(doc), True
        if created:
            await self.events.append(run["_id"], ws_id, "run.queued",
                                     {"workflow_version": version, "source": req.source,
                                      "steps": len(definition.get("steps") or [])})
            await self.audit.record(ws_id, user_id, "run.create", "run", run["_id"], {"workflow_id": w["_id"]})
        return run, created
