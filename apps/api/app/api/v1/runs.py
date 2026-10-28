import asyncio
import json

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from app.api.deps import Ctx, db_dep, rate_limit, require
from app.schemas.common import Page
from app.schemas.runs import TERMINAL, RunCreate, RunEventOut, RunOut
from app.services.runs import RunService, present_run

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunOut, status_code=202, dependencies=[Depends(rate_limit("runs", 120))])
async def create_run(body: RunCreate, response: Response, ctx: Ctx = Depends(require("runs:create")),
                     db=Depends(db_dep),
                     idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=128),
                     wait_seconds: float = Query(0, ge=0, le=60, description="Block up to N seconds for a result")):
    """Enqueues the run and returns immediately (202). Execution happens in the worker.

    With `wait_seconds`, the request waits (polling the run, never executing it) until the run is
    terminal or the wait elapses: 200 with the finished run, or 202 with the in-flight run."""
    svc = RunService(db)
    run, created = await svc.create(ctx.workspace_id, ctx.user_id, ctx.role, body, idempotency_key)
    if not created:
        response.status_code = 200
    response.headers["Location"] = f"/api/v1/runs/{run['_id']}"
    if wait_seconds and run["status"] not in TERMINAL:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while loop.time() < deadline:
            await asyncio.sleep(0.25)
            run = await svc.get(ctx.workspace_id, run["_id"])
            if run["status"] in TERMINAL:
                break
    if run["status"] in TERMINAL:
        response.status_code = 200
    return present_run(run)


@router.get("", response_model=Page[RunOut])
async def list_runs(ctx: Ctx = Depends(require("runs:read")), db=Depends(db_dep),
                    status: str | None = Query(None, max_length=32), agent_id: str | None = Query(None, max_length=64),
                    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    items, total = await RunService(db).list(ctx.workspace_id, status, agent_id, limit, offset)
    return {"items": [present_run(r) for r in items], "total": total, "limit": limit, "offset": offset}


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, ctx: Ctx = Depends(require("runs:read")), db=Depends(db_dep)):
    return present_run(await RunService(db).get(ctx.workspace_id, run_id))


@router.post("/{run_id}/cancel", response_model=RunOut)
async def cancel_run(run_id: str, ctx: Ctx = Depends(require("runs:cancel")), db=Depends(db_dep)):
    return present_run(await RunService(db).cancel(ctx.workspace_id, ctx.user_id, run_id))


@router.get("/{run_id}/events", response_model=list[RunEventOut])
async def list_events(run_id: str, ctx: Ctx = Depends(require("runs:read")), db=Depends(db_dep),
                      after: int = Query(0, ge=0)):
    svc = RunService(db)
    await svc.get(ctx.workspace_id, run_id)
    return await svc.events.after(ctx.workspace_id, run_id, after)


@router.get("/{run_id}/stream")
async def stream_events(run_id: str, request: Request, ctx: Ctx = Depends(require("runs:read")),
                        db=Depends(db_dep), after: int = Query(0, ge=0)):
    """Server-Sent Events. Resumable via Last-Event-ID. Implemented by polling the
    append-only event log (works on any MongoDB deployment, no change streams required)."""
    svc = RunService(db)
    await svc.get(ctx.workspace_id, run_id)
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else after

    async def gen():
        nonlocal cursor
        idle = 0.0
        while True:
            if await request.is_disconnected():
                return
            events = await svc.events.after(ctx.workspace_id, run_id, cursor)
            for e in events:
                cursor = e["seq"]
                data = {"seq": e["seq"], "type": e["type"], "ts": e["ts"].isoformat(), "data": e["data"]}
                yield f"id: {e['seq']}\nevent: run_event\ndata: {json.dumps(data, default=str)}\n\n"
            run = await svc.runs.get(ctx.workspace_id, run_id)
            if not events and run and run["status"] in TERMINAL:
                yield f"event: end\ndata: {json.dumps({'status': run['status']})}\n\n"
                return
            await asyncio.sleep(0.5)
            idle += 0.5
            if idle >= 15:
                idle = 0
                yield ": keep-alive\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
