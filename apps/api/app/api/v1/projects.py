from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import Ctx, db_dep, require
from app.schemas.common import Page
from app.schemas.projects import (ProjectCreate, ProjectDocumentCreate, ProjectDocumentOut,
                                  ProjectDocumentUpdate, ProjectOut, ProjectPlanStart, ProjectPlanStartOut,
                                  ProjectUpdate)
from app.services.projects import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Page[ProjectOut])
async def list_projects(ctx: Ctx = Depends(require("agents:read")), db: AsyncDatabase = Depends(db_dep),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = await ProjectService(db).list(ctx.workspace_id, limit, offset)
    return {"items": [ProjectService(db).present(p) for p in items], "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, ctx: Ctx = Depends(require("agents:write")),
                         db: AsyncDatabase = Depends(db_dep)):
    return ProjectService(db).present(await ProjectService(db).create(ctx.workspace_id, ctx.user_id, body))


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, ctx: Ctx = Depends(require("agents:read")),
                      db: AsyncDatabase = Depends(db_dep)):
    svc = ProjectService(db)
    return svc.present(await svc.get(ctx.workspace_id, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectUpdate, ctx: Ctx = Depends(require("agents:write")),
                         db: AsyncDatabase = Depends(db_dep)):
    svc = ProjectService(db)
    return svc.present(await svc.update(ctx.workspace_id, ctx.user_id, project_id, body))


@router.post("/{project_id}/documents", response_model=ProjectOut, status_code=201)
async def create_document(project_id: str, body: ProjectDocumentCreate, ctx: Ctx = Depends(require("agents:write")),
                          db: AsyncDatabase = Depends(db_dep)):
    svc = ProjectService(db)
    return svc.present(await svc.add_document(ctx.workspace_id, ctx.user_id, project_id, body))


@router.patch("/{project_id}/documents/{document_id}", response_model=ProjectOut)
async def update_document(project_id: str, document_id: str, body: ProjectDocumentUpdate,
                          ctx: Ctx = Depends(require("agents:write")), db: AsyncDatabase = Depends(db_dep)):
    svc = ProjectService(db)
    return svc.present(await svc.update_document(ctx.workspace_id, ctx.user_id, project_id, document_id, body))


@router.post("/{project_id}/plan", response_model=ProjectPlanStartOut, status_code=202)
async def start_planning(project_id: str, body: ProjectPlanStart, ctx: Ctx = Depends(require("runs:create")),
                         db: AsyncDatabase = Depends(db_dep)):
    svc = ProjectService(db)
    result = await svc.start_planning(ctx.workspace_id, ctx.user_id, ctx.role, project_id,
                                      body.feedback, body.document_ids)
    return result
