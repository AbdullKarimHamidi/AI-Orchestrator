from fastapi import APIRouter, Depends, Header, Query, Response

from app.api.deps import Ctx, db_dep, rate_limit, require
from app.schemas.common import Page
from app.schemas.runs import RunOut
from app.schemas.workflows import (
    WorkflowCreate,
    WorkflowOut,
    WorkflowPublish,
    WorkflowRunCreate,
    WorkflowUpdate,
    WorkflowVersionOut,
)
from app.services.runs import RunService, present_run
from app.services.workflows import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=Page[WorkflowOut])
async def list_workflows(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep),
                         status: str | None = Query(None, pattern="^(draft|published|archived)$"),
                         limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    svc = WorkflowService(db)
    f: dict = {"deleted": False}
    if status:
        f["status"] = status
    items, total = await svc.workflows.list(ctx.workspace_id, f, sort=[("updated_at", -1)], limit=limit, offset=offset)
    return {"items": [await svc.present(ctx.workspace_id, w) for w in items], "total": total,
            "limit": limit, "offset": offset}


@router.post("", response_model=WorkflowOut, status_code=201)
async def create_workflow(body: WorkflowCreate, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    svc = WorkflowService(db)
    return await svc.present(ctx.workspace_id, await svc.create(ctx.workspace_id, ctx.user_id, body))


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    svc = WorkflowService(db)
    return await svc.present(ctx.workspace_id, await svc.get(ctx.workspace_id, workflow_id))


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(workflow_id: str, body: WorkflowUpdate, ctx: Ctx = Depends(require("agents:write")),
                          db=Depends(db_dep)):
    svc = WorkflowService(db)
    return await svc.present(ctx.workspace_id, await svc.update(ctx.workspace_id, ctx.user_id, workflow_id, body))


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    await WorkflowService(db).delete(ctx.workspace_id, ctx.user_id, workflow_id)


@router.get("/{workflow_id}/validate", response_model=dict)
async def validate_workflow(workflow_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    """Checks the draft's references (agents published, tools and knowledge bases exist)."""
    svc = WorkflowService(db)
    w = await svc.get(ctx.workspace_id, workflow_id)
    problems = await svc.validate_references(ctx.workspace_id, w["draft"])
    return {"valid": not problems, "problems": problems}


@router.post("/{workflow_id}/publish", response_model=WorkflowOut)
async def publish_workflow(workflow_id: str, body: WorkflowPublish, ctx: Ctx = Depends(require("agents:publish")),
                           db=Depends(db_dep)):
    svc = WorkflowService(db)
    w = await svc.publish(ctx.workspace_id, ctx.user_id, workflow_id, body.note)
    return await svc.present(ctx.workspace_id, w)


@router.post("/{workflow_id}/archive", response_model=WorkflowOut)
async def archive_workflow(workflow_id: str, ctx: Ctx = Depends(require("agents:publish")), db=Depends(db_dep)):
    svc = WorkflowService(db)
    w = await svc.set_archived(ctx.workspace_id, ctx.user_id, workflow_id, True)
    return await svc.present(ctx.workspace_id, w)


@router.post("/{workflow_id}/restore", response_model=WorkflowOut)
async def restore_workflow(workflow_id: str, ctx: Ctx = Depends(require("agents:publish")), db=Depends(db_dep)):
    svc = WorkflowService(db)
    w = await svc.set_archived(ctx.workspace_id, ctx.user_id, workflow_id, False)
    return await svc.present(ctx.workspace_id, w)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
async def list_versions(workflow_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return [{**v, "id": v["_id"]} for v in await WorkflowService(db).list_versions(ctx.workspace_id, workflow_id)]


@router.post("/{workflow_id}/runs", response_model=RunOut, status_code=202,
             dependencies=[Depends(rate_limit("runs", 120))])
async def run_workflow(workflow_id: str, body: WorkflowRunCreate, response: Response,
                       ctx: Ctx = Depends(require("runs:create")), db=Depends(db_dep),
                       idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128)):
    """Queues a workflow run (202). Follow it with GET /runs/{id} or the SSE stream."""
    run, created = await WorkflowService(db).create_run(ctx.workspace_id, ctx.user_id, ctx.role, workflow_id, body,
                                                        idempotency_key)
    if not created:
        response.status_code = 200
    response.headers["Location"] = f"/api/v1/runs/{run['_id']}"
    return present_run(run)


@router.get("/{workflow_id}/runs", response_model=Page[RunOut])
async def list_workflow_runs(workflow_id: str, ctx: Ctx = Depends(require("runs:read")), db=Depends(db_dep),
                             limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = await RunService(db).list(ctx.workspace_id, None, None, limit, offset, workflow_id=workflow_id)
    return {"items": [present_run(r) for r in items], "total": total, "limit": limit, "offset": offset}
