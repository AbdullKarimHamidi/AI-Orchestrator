from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.schemas.agents import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    AgentVersionOut,
    CloneRequest,
    PublishRequest,
    RollbackRequest,
    VersionDiff,
)
from app.schemas.common import Page
from app.services.agents import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


def _v(v: dict) -> dict:
    return {**v, "id": v["_id"]}


@router.get("", response_model=Page[AgentOut])
async def list_agents(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep),
                      status: str | None = Query(None, pattern="^(draft|published|paused|retired)$"),
                      q: str | None = Query(None, max_length=100),
                      limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    import re

    svc = AgentService(db)
    f: dict = {"deleted": False}
    if status:
        f["status"] = status
    if q:
        f["name_lower"] = {"$regex": re.escape(q.lower())}
    items, total = await svc.agents.list(ctx.workspace_id, f, sort=[("updated_at", -1)], limit=limit, offset=offset)
    return {"items": [await svc.present(ctx.workspace_id, a) for a in items], "total": total,
            "limit": limit, "offset": offset}


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentCreate, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.create(ctx.workspace_id, ctx.user_id, body))


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.get(ctx.workspace_id, agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: str, body: AgentUpdate, ctx: Ctx = Depends(require("agents:write")),
                       db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.update(ctx.workspace_id, ctx.user_id, agent_id, body))


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    await AgentService(db).delete(ctx.workspace_id, ctx.user_id, agent_id)


@router.post("/{agent_id}/clone", response_model=AgentOut, status_code=201)
async def clone_agent(agent_id: str, body: CloneRequest, ctx: Ctx = Depends(require("agents:write")),
                      db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.clone(ctx.workspace_id, ctx.user_id, agent_id, body.name))


@router.post("/{agent_id}/publish", response_model=AgentOut)
async def publish_agent(agent_id: str, body: PublishRequest, ctx: Ctx = Depends(require("agents:publish")),
                        db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.publish(ctx.workspace_id, ctx.user_id, agent_id, body.note))


async def _transition(agent_id: str, action: str, ctx: Ctx, db) -> dict:
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id, await svc.transition(ctx.workspace_id, ctx.user_id, agent_id, action))


@router.post("/{agent_id}/pause", response_model=AgentOut)
async def pause_agent(agent_id: str, ctx: Ctx = Depends(require("agents:publish")), db=Depends(db_dep)):
    return await _transition(agent_id, "pause", ctx, db)


@router.post("/{agent_id}/resume", response_model=AgentOut)
async def resume_agent(agent_id: str, ctx: Ctx = Depends(require("agents:publish")), db=Depends(db_dep)):
    return await _transition(agent_id, "resume", ctx, db)


@router.post("/{agent_id}/retire", response_model=AgentOut)
async def retire_agent(agent_id: str, ctx: Ctx = Depends(require("agents:publish")), db=Depends(db_dep)):
    return await _transition(agent_id, "retire", ctx, db)


@router.get("/{agent_id}/versions", response_model=list[AgentVersionOut])
async def list_versions(agent_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return [_v(v) for v in await AgentService(db).list_versions(ctx.workspace_id, agent_id)]


@router.get("/{agent_id}/versions/compare", response_model=VersionDiff)
async def compare_versions(agent_id: str, a: int = Query(..., ge=1), b: int = Query(..., ge=1),
                           ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    changes = await AgentService(db).compare(ctx.workspace_id, agent_id, a, b)
    return {"from_version": a, "to_version": b, "changes": changes}


@router.post("/{agent_id}/rollback", response_model=AgentOut)
async def rollback(agent_id: str, body: RollbackRequest, ctx: Ctx = Depends(require("agents:publish")),
                   db=Depends(db_dep)):
    svc = AgentService(db)
    return await svc.present(ctx.workspace_id,
                             await svc.rollback(ctx.workspace_id, ctx.user_id, agent_id, body.version))
