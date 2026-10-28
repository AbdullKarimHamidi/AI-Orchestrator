from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.schemas.common import Page
from app.schemas.memory import ForgetRequest, ForgetResult, MemoryCreate, MemoryOut, MemoryScopeOut, MemoryUpdate
from app.services.memory import MemoryService, present_memory

router = APIRouter(prefix="/memories", tags=["memory"])


@router.get("", response_model=Page[MemoryOut])
async def list_memories(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep),
                        agent_id: str | None = Query(None, max_length=64),
                        scope: str | None = Query(None, max_length=120),
                        q: str | None = Query(None, max_length=200),
                        limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = await MemoryService(db).find(ctx.workspace_id, agent_id, scope, q, limit, offset)
    return {"items": [present_memory(m) for m in items], "total": total, "limit": limit, "offset": offset}


@router.get("/scopes", response_model=list[MemoryScopeOut])
async def list_scopes(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep),
                      agent_id: str | None = Query(None, max_length=64)):
    return await MemoryService(db).mem.scopes(ctx.workspace_id, agent_id)


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(body: MemoryCreate, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    return present_memory(await MemoryService(db).create(ctx.workspace_id, ctx.user_id, body.agent_id, body.scope,
                                                         body.content, body.tags, body.ttl_days))


@router.patch("/{memory_id}", response_model=MemoryOut)
async def update_memory(memory_id: str, body: MemoryUpdate, ctx: Ctx = Depends(require("agents:write")),
                        db=Depends(db_dep)):
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    return present_memory(await MemoryService(db).update(ctx.workspace_id, ctx.user_id, memory_id, fields))


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    await MemoryService(db).delete(ctx.workspace_id, ctx.user_id, memory_id)


@router.post("/forget", response_model=ForgetResult)
async def forget(body: ForgetRequest, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    """Deletion request: removes every memory of an agent, or of one scope (e.g. one end user)."""
    return {"deleted": await MemoryService(db).forget(ctx.workspace_id, ctx.user_id, body.agent_id, body.scope)}
