"""Project Creator persistence and planning-run orchestration.

Planning agents are enqueued independently so the existing worker executes them concurrently.
Project and document mutations are workspace scoped and use optimistic revision checks.
"""
import asyncio
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.repositories.agents import AgentRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.projects import ProjectRepository
from app.repositories.runs import RunRepository
from app.schemas.projects import ProjectCreate, ProjectDocumentCreate, ProjectDocumentUpdate, ProjectUpdate
from app.schemas.runs import RunCreate
from app.services.runs import RunService


class ProjectService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.projects = ProjectRepository(db)
        self.agents = AgentRepository(db)
        self.runs = RunRepository(db)
        self.audit = AuditRepository(db)

    def present(self, project: dict) -> dict:
        return {**project, "id": project["_id"]}

    async def get(self, ws_id: str, project_id: str) -> dict:
        project = await self.projects.get(ws_id, project_id)
        if not project or project.get("deleted"):
            raise NotFound("Project not found")
        # Reflect planning-run progress in the durable project record. A run can only belong
        # to the same workspace, and the UI receives a compact status snapshot.
        changed = False
        for item in project.get("planning_runs", []):
            run = await self.runs.get(ws_id, item["run_id"])
            if run and item.get("status") != run["status"]:
                item["status"] = run["status"]
                item["updated_at"] = run.get("updated_at") or run.get("finished_at") or now()
                changed = True
                if run["status"] == "completed" and not item.get("document_id"):
                    output = run.get("output") or {}
                    content = output.get("text") or output.get("content") or output.get("answer") or ""
                    if isinstance(content, (dict, list)):
                        import json
                        content = json.dumps(content, ensure_ascii=False, indent=2)
                    if isinstance(content, str) and content.strip():
                        title = f"{item.get('agent_name', 'Planning agent')} — {item.get('purpose', 'Project plan')}"
                        document = {"id": new_id("doc"), "title": title[:200], "kind": item.get("purpose", "plan"),
                                    "content": content[:100000], "feedback": "", "status": "in_review",
                                    "revision": 1, "created_at": now(), "updated_at": now()}
                        project.setdefault("documents", []).append(document)
                        item["document_id"] = document["id"]
            if run and run.get("error") and item.get("error") != run["error"]:
                item["error"] = run["error"]
                changed = True
        if changed:
            # A compare-and-swap prevents concurrent polling requests from persisting duplicate
            # documents or overwriting a user's project edits.
            if project.get("status") == "planning" and project.get("planning_runs"):
                terminal = {"completed", "failed", "cancelled", "timed_out"}
                if all(item.get("status") in terminal for item in project["planning_runs"]):
                    project["status"] = "ready" if project.get("documents") and all(
                        item.get("status") == "completed" for item in project["planning_runs"]
                    ) else "blocked"
            saved = await self.projects.col.update_one(
                {"_id": project_id, "workspace_id": ws_id, "revision": project["revision"]},
                {"$set": {"planning_runs": project.get("planning_runs", []),
                          "documents": project.get("documents", []), "status": project.get("status"),
                          "updated_at": now()}, "$inc": {"revision": 1}})
            if saved.modified_count != 1:
                latest = await self.projects.get(ws_id, project_id)
                if latest:
                    return latest
            else:
                project["revision"] += 1
        return project

    async def list(self, ws_id: str, limit: int, offset: int) -> tuple[list[dict], int]:
        return await self.projects.list(ws_id, {"deleted": False}, sort=[("updated_at", -1)],
                                        limit=limit, offset=offset)

    async def create(self, ws_id: str, user_id: str, req: ProjectCreate) -> dict:
        all_agent_ids = set(req.planning_agent_ids + req.supervisor_agent_ids +
                            [agent_id for team in req.teams for agent_id in team.agent_ids])
        for agent_id in all_agent_ids:
            agent = await self.agents.get(ws_id, agent_id)
            if not agent:
                raise Unprocessable(f"Agent '{agent_id}' was not found in this workspace", code="PROJECT_AGENT_INVALID")
            if agent.get("status") != "published" or not agent.get("published_version"):
                raise Unprocessable(f"Agent '{agent['name']}' must be published before project assignment",
                                    code="PROJECT_AGENT_NOT_PUBLISHED")
        t = now()
        doc = {"_id": new_id("prj"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "idea": req.idea, "description": req.description, "status": "planning",
               "planning_agent_ids": req.planning_agent_ids, "supervisor_agent_ids": req.supervisor_agent_ids,
               "teams": [team.model_dump(mode="json") for team in req.teams], "documents": [], "planning_runs": [],
               "revision": 1, "created_by": user_id, "created_at": t, "updated_at": t, "deleted": False}
        try:
            await self.projects.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A project with this name already exists", code="PROJECT_NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "project.create", "project", doc["_id"])
        return doc

    async def update(self, ws_id: str, user_id: str, project_id: str, req: ProjectUpdate) -> dict:
        current = await self.get(ws_id, project_id)
        fields: dict[str, Any] = {}
        for field in ("name", "idea", "description", "status", "planning_agent_ids", "supervisor_agent_ids", "teams"):
            value = getattr(req, field)
            if value is not None:
                if field in ("planning_agent_ids", "supervisor_agent_ids"):
                    if len(value) != len(set(value)):
                        raise Unprocessable(f"{field} must be unique", code="DUPLICATE_AGENT")
                    for agent_id in value:
                        agent = await self.agents.get(ws_id, agent_id)
                        if not agent or agent.get("status") != "published" or not agent.get("published_version"):
                            raise Unprocessable(f"Agent '{agent_id}' must be published in this workspace",
                                                code="PROJECT_AGENT_INVALID")
                if field == "teams":
                    for team in value:
                        for agent_id in team.agent_ids:
                            agent = await self.agents.get(ws_id, agent_id)
                            if not agent or agent.get("status") != "published" or not agent.get("published_version"):
                                raise Unprocessable(f"Agent '{agent_id}' must be published in this workspace",
                                                    code="PROJECT_AGENT_INVALID")
                    value = [team.model_dump(mode="json") for team in value]
                if field == "name":
                    fields["name_lower"] = value.lower()
                fields[field] = value
        updated = await self.projects.update_if_revision(ws_id, project_id, req.revision, fields)
        if not updated:
            raise Conflict("Project changed since you opened it. Reload and retry.",
                           code="REVISION_MISMATCH", details={"current_revision": current["revision"]})
        await self.audit.record(ws_id, user_id, "project.update", "project", project_id, {"fields": sorted(fields)})
        return updated

    async def delete(self, ws_id: str, user_id: str, project_id: str) -> None:
        """Soft-delete a project, preserving its documents and audit trail."""
        project = await self.get(ws_id, project_id)
        run_service = RunService(self.db)
        terminal = {"completed", "failed", "cancelled", "timed_out"}
        for item in project.get("planning_runs", []):
            if item.get("status") not in terminal:
                try:
                    await run_service.cancel(ws_id, user_id, item["run_id"])
                except (Conflict, NotFound):
                    # A worker may finish the run while the project is being deleted.
                    pass

        result = await self.projects.col.update_one(
            {"_id": project_id, "workspace_id": ws_id, "deleted": False},
            {"$set": {"deleted": True, "deleted_at": now(), "updated_at": now()},
             "$inc": {"revision": 1}},
        )
        if result.modified_count != 1:
            raise NotFound("Project not found")
        await self.audit.record(ws_id, user_id, "project.delete", "project", project_id)


    async def add_document(self, ws_id: str, user_id: str, project_id: str, req: ProjectDocumentCreate) -> dict:
        project = await self.get(ws_id, project_id)
        t = now()
        document = {"id": new_id("doc"), **req.model_dump(mode="json"), "revision": 1, "created_at": t, "updated_at": t}
        await self.projects.col.update_one({"_id": project_id, "workspace_id": ws_id, "revision": project["revision"]},
                                           {"$push": {"documents": document},
                                            "$inc": {"revision": 1}, "$set": {"updated_at": t}})
        await self.audit.record(ws_id, user_id, "project.document.create", "project", project_id,
                                {"document_id": document["id"]})
        return await self.get(ws_id, project_id)

    async def update_document(self, ws_id: str, user_id: str, project_id: str, document_id: str,
                              req: ProjectDocumentUpdate) -> dict:
        project = await self.get(ws_id, project_id)
        docs = project.get("documents", [])
        idx = next((i for i, d in enumerate(docs) if d["id"] == document_id), None)
        if idx is None:
            raise NotFound("Project document not found")
        doc = docs[idx]
        if doc["revision"] != req.revision:
            raise Conflict("Document changed since you opened it. Reload and retry.", code="REVISION_MISMATCH")
        updates = req.model_dump(exclude_unset=True, exclude={"revision"})
        docs[idx] = {**doc, **updates, "revision": doc["revision"] + 1, "updated_at": now()}
        result = await self.projects.col.update_one(
            {"_id": project_id, "workspace_id": ws_id, "revision": project["revision"]},
            {"$set": {"documents": docs, "updated_at": now()}, "$inc": {"revision": 1}})
        if result.modified_count != 1:
            raise Conflict("Project changed during document save. Reload and retry.", code="REVISION_MISMATCH")
        await self.audit.record(ws_id, user_id, "project.document.update", "project", project_id,
                                {"document_id": document_id, "fields": sorted(updates)})
        return await self.get(ws_id, project_id)

    async def start_planning(self, ws_id: str, user_id: str, role: str, project_id: str,
                             feedback: str = "", document_ids: list[str] | None = None) -> dict:
        project = await self.get(ws_id, project_id)
        selected_docs = [d for d in project.get("documents", []) if not document_ids or d["id"] in document_ids]
        doc_context = "\n\n".join(f"## {d['title']}\n{d.get('content', '')}" for d in selected_docs)
        prompt = (
            "You are a senior project-planning agent. Produce a concrete, implementation-ready project plan. "
            "Return clear sections for architecture, requirements, data model, API contracts, UI/UX, milestones, "
            "testing strategy, risks, and acceptance criteria. Do not claim implementation is complete.\n\n"
            f"PROJECT NAME: {project['name']}\nPROJECT IDEA:\n{project['idea']}\n"
            f"DESCRIPTION:\n{project.get('description', '')}\n"
            f"USER FEEDBACK / CHANGE REQUEST:\n{feedback or '(none)'}\n"
            f"EXISTING DOCUMENTS TO REVISE:\n{doc_context or '(none yet)'}\n"
            "Create or revise the plan based on all feedback. Clearly list assumptions and open questions."
        )
        from app.services.rbac import has_permission
        if not has_permission(role, "runs:create"):
            from app.core.exceptions import Forbidden
            raise Forbidden("Role lacks permission to start planning runs")
        agent_ids = project["planning_agent_ids"]
        svc = RunService(self.db)
        # Queue concurrently; workers independently claim these runs.
        results = await asyncio.gather(*[
            svc.create(ws_id, user_id, role, RunCreate(agent_id=agent_id, source="published",
                                                       input={"message": prompt,
                                                              "variables": {"project_id": project_id,
                                                                            "purpose": "Project plan",
                                                                            "feedback": feedback}}), None)
            for agent_id in agent_ids
        ], return_exceptions=True)
        queued = []
        errors = []
        for agent_id, result in zip(agent_ids, results, strict=False):
            if isinstance(result, Exception):
                errors.append({"agent_id": agent_id, "error": str(result)})
                continue
            run, _ = result
            agent = await self.agents.get(ws_id, agent_id)
            queued.append({"run_id": run["_id"], "agent_id": agent_id, "agent_name": agent["name"],
                           "purpose": "Project plan", "status": run["status"], "document_id": None,
                           "error": None, "created_at": now(), "updated_at": now()})
        if not queued:
            raise Unprocessable("No planning runs could be queued", code="PLANNING_START_FAILED",
                                details={"errors": errors})
        await self.projects.col.update_one({"_id": project_id, "workspace_id": ws_id},
                                           {"$push": {"planning_runs": {"$each": queued}},
                                            "$set": {"status": "planning", "updated_at": now()}})
        await self.audit.record(ws_id, user_id, "project.planning.start", "project", project_id,
                                {"run_ids": [r["run_id"] for r in queued], "errors": errors})
        return {"project_id": project_id, "run_ids": [r["run_id"] for r in queued],
                "message": f"Queued {len(queued)} planning agent(s) in parallel.", "errors": errors}
