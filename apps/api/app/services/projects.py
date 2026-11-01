"""Project Creator persistence and planning-run orchestration.

Planning agents are enqueued independently so the existing worker executes them concurrently.
Project and document mutations are workspace scoped and use optimistic revision checks.
"""
from __future__ import annotations

import asyncio
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.orchestration import project_build
from app.repositories.agents import AgentRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.projects import ProjectRepository
from app.repositories.providers import ProviderRepository
from app.repositories.runs import RunRepository
from app.schemas.projects import (
    ProjectBuildStart,
    ProjectCreate,
    ProjectDocumentCreate,
    ProjectDocumentUpdate,
    ProjectFileWrite,
    ProjectUpdate,
)
from app.schemas.runs import TERMINAL, RunCreate
from app.schemas.workflows import WorkflowCreate, WorkflowDefinition, WorkflowRunCreate, WorkflowUpdate
from app.services.runs import RunService
from app.services.workflows import WorkflowService


class ProjectService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.projects = ProjectRepository(db)
        self.agents = AgentRepository(db)
        self.runs = RunRepository(db)
        self.providers = ProviderRepository(db)
        self.audit = AuditRepository(db)

    def present(self, project: dict) -> dict:
        return {**project, "id": project["_id"]}

    async def _planning_model(self, ws_id: str, ref) -> dict | None:
        """Validates the provider/model chosen for planning and returns it as stored on the project."""
        if ref is None:
            return None
        provider = await self.providers.get(ws_id, ref.provider_id)
        if not provider:
            raise Unprocessable("The selected model provider does not exist in this workspace",
                                code="PROVIDER_NOT_FOUND")
        if not provider.get("enabled", True):
            raise Unprocessable(f"The provider '{provider['name']}' is disabled. Enable it on the Models page.",
                                code="PROVIDER_DISABLED")
        model = ref.model.strip()
        if provider.get("allowed_models") and model not in provider["allowed_models"]:
            raise Unprocessable(f"Model '{model}' is not allowed on {provider['name']}", code="MODEL_NOT_ALLOWED")
        return {"provider_id": provider["_id"], "model": model, "provider_name": provider["name"]}

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
        if await self._sync_builds(ws_id, project):
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
                          "build_runs": project.get("build_runs", []), "files": project.get("files", []),
                          "updated_at": now()}, "$inc": {"revision": 1}})
            if saved.modified_count != 1:
                latest = await self.projects.get(ws_id, project_id)
                if latest:
                    return latest
            else:
                project["revision"] += 1
        return project

    async def _sync_builds(self, ws_id: str, project: dict) -> bool:
        """Copies build-run progress onto the project; a completed run's files are merged in."""
        changed = False
        for item in project.get("build_runs", []):
            if item.get("status") in TERMINAL:
                continue
            run = await self.runs.get(ws_id, item["run_id"])
            if not run or run["status"] == item.get("status"):
                continue
            item["status"] = run["status"]
            item["updated_at"] = now()
            item["error"] = run.get("error")
            changed = True
            if run["status"] == "completed":
                output = run.get("output") or {}
                written = project_build.files_from_output(output, project_build.file_steps(run.get("config") or {}))
                by_path = {f["path"]: f for f in project.get("files", [])}
                for path, content in written.items():
                    by_path[path] = {"path": path, "content": content, "updated_at": now(),
                                     "updated_by": "agents", "round": item.get("round")}
                project["files"] = sorted(by_path.values(), key=lambda f: f["path"])[:project_build.MAX_FILES]
                steps = output.get("steps") or {}
                review = (steps.get("plan_check") or {}).get("text") or ""
                item["files_written"] = sorted(written)
                item["summary"] = str((steps.get("director") or {}).get("text") or output.get("text") or "")[:4000]
                item["review"] = review[:8000]
                item["verdict"] = ("complete" if "VERDICT: COMPLETE" in review.upper() else
                                   "incomplete" if "VERDICT: INCOMPLETE" in review.upper() else None)
                if project.get("status") in ("ready", "planning", "blocked"):
                    project["status"] = "in_progress"
                if item["verdict"] == "complete":
                    project["status"] = "completed"
        return changed

    async def start_build(self, ws_id: str, user_id: str, role: str, project_id: str,
                          req: ProjectBuildStart) -> dict:
        """Builds (or rebuilds) the project's team workflow from its build team and runs it."""
        from app.services.rbac import has_permission
        if not has_permission(role, "runs:create") or not has_permission(role, "agents:write"):
            from app.core.exceptions import Forbidden
            raise Forbidden("Starting a build needs permission to create workflows and runs")
        project = await self.get(ws_id, project_id)
        if any(b.get("status") not in TERMINAL for b in project.get("build_runs", [])):
            raise Conflict("A build round is still running. Wait for it or cancel it first.", code="BUILD_RUNNING")
        if req.planning_model is not None:
            project["planning_model"] = await self._planning_model(ws_id, req.planning_model)
        elif project.get("planning_model"):
            from app.schemas.agents import ModelRef
            pm = project["planning_model"]
            project["planning_model"] = await self._planning_model(
                ws_id, ModelRef(provider_id=pm["provider_id"], model=pm["model"]))
        team_agents = [a for t in project.get("teams", []) for a in [*t.get("agent_ids", []), t.get("lead_agent_id")]]
        await self._require_published(ws_id, [project.get("director_agent_id"), *team_agents,
                                              *project.get("reviewer_agent_ids", [])])
        names = {a["_id"]: a["name"] for a in [await self.agents.get(ws_id, x) for x in set(filter(None, team_agents))]
                 if a}
        try:
            raw = project_build.build_definition(project, names)
            definition = WorkflowDefinition.model_validate(raw)
        except ValueError as exc:
            raise Unprocessable(str(exc).splitlines()[-1] if "validation error" in str(exc) else str(exc),
                                code="BUILD_TEAM_INVALID") from exc

        wf_svc = WorkflowService(self.db)
        wf = None
        if project.get("build_workflow_id"):
            try:
                wf = await wf_svc.get(ws_id, project["build_workflow_id"])
            except NotFound:
                wf = None
        if wf is None or wf.get("deleted"):
            wf = await wf_svc.create(ws_id, user_id, WorkflowCreate(
                name=f"{project['name']} build team"[:120], description=f"Build team for project {project['name']}",
                definition=definition))
        else:
            wf = await wf_svc.update(ws_id, user_id, wf["_id"], WorkflowUpdate(revision=wf["revision"],
                                                                               definition=definition))
        try:
            await wf_svc.publish(ws_id, user_id, wf["_id"], "Project build")
        except Conflict as exc:
            if exc.code != "NO_CHANGES":
                raise
        files = {f["path"]: f["content"] for f in project.get("files", [])}
        brief = project_build.build_brief(project, files, req.instructions)
        run, _ = await wf_svc.create_run(ws_id, user_id, role, wf["_id"], WorkflowRunCreate(
            input={"message": brief[:100_000], "variables": {"project_id": project_id}}), None)
        n = len(project.get("build_runs", [])) + 1
        item = {"run_id": run["_id"], "workflow_id": wf["_id"], "round": n, "status": run["status"],
                "instructions": req.instructions[:4000], "files_written": [], "summary": "", "review": "",
                "verdict": None, "error": None, "created_at": now(), "updated_at": now()}
        updates: dict[str, Any] = {"build_workflow_id": wf["_id"], "status": "in_progress", "updated_at": now()}
        if req.planning_model is not None:
            updates["planning_model"] = project["planning_model"]
        await self.projects.col.update_one({"_id": project_id, "workspace_id": ws_id},
                                           {"$push": {"build_runs": item}, "$set": updates, "$inc": {"revision": 1}})
        await self.audit.record(ws_id, user_id, "project.build.start", "project", project_id,
                                {"run_id": run["_id"], "workflow_id": wf["_id"]})
        return {"project_id": project_id, "run_id": run["_id"], "workflow_id": wf["_id"],
                "message": f"Build round {n} started: the teams are working in parallel."}

    async def write_file(self, ws_id: str, user_id: str, project_id: str, req: ProjectFileWrite) -> dict:
        path = project_build.clean_path(req.path)
        if not path:
            raise Unprocessable("Use a relative path made of letters, numbers, '-', '_', '.' and '/'",
                                code="INVALID_PATH")
        project = await self.get(ws_id, project_id)
        files = [f for f in project.get("files", []) if f["path"] != path]
        if len(files) >= project_build.MAX_FILES:
            raise Unprocessable("This project already has the maximum number of files", code="TOO_MANY_FILES")
        files.append({"path": path, "content": req.content, "updated_at": now(), "updated_by": user_id,
                      "round": None})
        await self._save_files(ws_id, project, sorted(files, key=lambda f: f["path"]))
        await self.audit.record(ws_id, user_id, "project.file.write", "project", project_id, {"path": path})
        return await self.get(ws_id, project_id)

    async def delete_file(self, ws_id: str, user_id: str, project_id: str, path: str) -> dict:
        project = await self.get(ws_id, project_id)
        files = [f for f in project.get("files", []) if f["path"] != path]
        if len(files) == len(project.get("files", [])):
            raise NotFound("File not found")
        await self._save_files(ws_id, project, files)
        await self.audit.record(ws_id, user_id, "project.file.delete", "project", project_id, {"path": path})
        return await self.get(ws_id, project_id)

    async def _save_files(self, ws_id: str, project: dict, files: list[dict]) -> None:
        saved = await self.projects.col.update_one(
            {"_id": project["_id"], "workspace_id": ws_id, "revision": project["revision"]},
            {"$set": {"files": files, "updated_at": now()}, "$inc": {"revision": 1}})
        if saved.modified_count != 1:
            raise Conflict("Project changed while saving. Reload and retry.", code="REVISION_MISMATCH")

    async def list(self, ws_id: str, limit: int, offset: int) -> tuple[list[dict], int]:
        return await self.projects.list(ws_id, {"deleted": False}, sort=[("updated_at", -1)],
                                        limit=limit, offset=offset)

    async def _require_published(self, ws_id: str, agent_ids) -> None:
        for agent_id in {a for a in agent_ids if a}:
            agent = await self.agents.get(ws_id, agent_id)
            if not agent or agent.get("deleted"):
                raise Unprocessable(f"Agent '{agent_id}' was not found in this workspace", code="PROJECT_AGENT_INVALID")
            if agent.get("status") != "published" or not agent.get("published_version"):
                raise Unprocessable(f"Agent '{agent['name']}' must be published before project assignment",
                                    code="PROJECT_AGENT_NOT_PUBLISHED")

    async def create(self, ws_id: str, user_id: str, req: ProjectCreate) -> dict:
        all_agent_ids = set(req.planning_agent_ids + req.supervisor_agent_ids + req.reviewer_agent_ids +
                            [agent_id for team in req.teams for agent_id in team.agent_ids] +
                            [team.lead_agent_id for team in req.teams if team.lead_agent_id] +
                            ([req.director_agent_id] if req.director_agent_id else []))
        for agent_id in all_agent_ids:
            agent = await self.agents.get(ws_id, agent_id)
            if not agent:
                raise Unprocessable(f"Agent '{agent_id}' was not found in this workspace", code="PROJECT_AGENT_INVALID")
            if agent.get("status") != "published" or not agent.get("published_version"):
                raise Unprocessable(f"Agent '{agent['name']}' must be published before project assignment",
                                    code="PROJECT_AGENT_NOT_PUBLISHED")
        planning_model = await self._planning_model(ws_id, req.planning_model)
        t = now()
        doc = {"_id": new_id("prj"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "idea": req.idea, "description": req.description, "status": "planning",
               "planning_agent_ids": req.planning_agent_ids, "supervisor_agent_ids": req.supervisor_agent_ids,
               "teams": [team.model_dump(mode="json") for team in req.teams], "documents": [], "planning_runs": [],
               "planning_model": planning_model, "director_agent_id": req.director_agent_id,
               "reviewer_agent_ids": req.reviewer_agent_ids, "files": [], "build_runs": [], "build_workflow_id": None,
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
                    await self._require_published(ws_id, [a for team in value for a in
                                                          [*team.agent_ids, team.lead_agent_id]])
                    value = [team.model_dump(mode="json") for team in value]
                if field == "name":
                    fields["name_lower"] = value.lower()
                fields[field] = value
        if req.director_agent_id is not None:
            await self._require_published(ws_id, [req.director_agent_id])
            fields["director_agent_id"] = req.director_agent_id or None
        if req.reviewer_agent_ids is not None:
            await self._require_published(ws_id, req.reviewer_agent_ids)
            fields["reviewer_agent_ids"] = list(dict.fromkeys(req.reviewer_agent_ids))
        if req.clear_planning_model:
            fields["planning_model"] = None
        elif req.planning_model is not None:
            fields["planning_model"] = await self._planning_model(ws_id, req.planning_model)
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
                             feedback: str = "", document_ids: list[str] | None = None,
                             planning_model=None) -> dict:
        project = await self.get(ws_id, project_id)
        model = await self._planning_model(ws_id, planning_model) if planning_model else project.get("planning_model")
        if model:
            # Re-check a stored choice: the provider may have been deleted or disabled since.
            from app.schemas.agents import ModelRef
            model = await self._planning_model(ws_id, ModelRef(provider_id=model["provider_id"], model=model["model"]))
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
                                                                            "feedback": feedback}}), None,
                       model_override={"provider_id": model["provider_id"], "model": model["model"]} if model else None)
            for agent_id in agent_ids
        ], return_exceptions=True)
        queued = []
        errors = []
        for agent_id, result in zip(agent_ids, results, strict=False):
            if isinstance(result, Exception):
                errors.append({"agent_id": agent_id, "error": getattr(result, "message", None) or str(result)})
                continue
            run, _ = result
            agent = await self.agents.get(ws_id, agent_id)
            queued.append({"run_id": run["_id"], "agent_id": agent_id, "agent_name": agent["name"],
                           "purpose": "Project plan", "status": run["status"], "document_id": None,
                           "model": run["config"]["model"]["model"],
                           "provider_id": run["config"]["model"]["provider_id"],
                           "error": None, "created_at": now(), "updated_at": now()})
        if not queued:
            reasons = "; ".join(e["error"] for e in errors)
            raise Unprocessable(f"No planning runs could be queued: {reasons}", code="PLANNING_START_FAILED",
                                details={"errors": errors})
        updates: dict[str, Any] = {"status": "planning", "updated_at": now()}
        if planning_model:
            updates["planning_model"] = model
        await self.projects.col.update_one({"_id": project_id, "workspace_id": ws_id},
                                           {"$push": {"planning_runs": {"$each": queued}},
                                            "$set": updates, "$inc": {"revision": 1}})
        await self.audit.record(ws_id, user_id, "project.planning.start", "project", project_id,
                                {"run_ids": [r["run_id"] for r in queued], "errors": errors})
        return {"project_id": project_id, "run_ids": [r["run_id"] for r in queued],
                "message": f"Queued {len(queued)} planning agent(s) in parallel.", "errors": errors}
