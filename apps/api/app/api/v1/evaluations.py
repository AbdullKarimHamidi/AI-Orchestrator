from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.schemas.evaluations import CompareOut, DatasetCreate, DatasetOut, DatasetUpdate, EvalRunCreate, EvalRunOut
from app.services.evaluations import EvaluationService, present_dataset, present_eval

router = APIRouter(tags=["evaluations"])


@router.get("/eval-datasets", response_model=list[DatasetOut])
async def list_datasets(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return [present_dataset(d) for d in await EvaluationService(db).list_datasets(ctx.workspace_id)]


@router.post("/eval-datasets", response_model=DatasetOut, status_code=201)
async def create_dataset(body: DatasetCreate, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    return present_dataset(await EvaluationService(db).create_dataset(ctx.workspace_id, ctx.user_id, body))


@router.get("/eval-datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return present_dataset(await EvaluationService(db).get_dataset(ctx.workspace_id, dataset_id))


@router.patch("/eval-datasets/{dataset_id}", response_model=DatasetOut)
async def update_dataset(dataset_id: str, body: DatasetUpdate, ctx: Ctx = Depends(require("agents:write")),
                         db=Depends(db_dep)):
    return present_dataset(await EvaluationService(db).update_dataset(ctx.workspace_id, ctx.user_id, dataset_id, body))


@router.delete("/eval-datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    await EvaluationService(db).delete_dataset(ctx.workspace_id, ctx.user_id, dataset_id)


@router.get("/eval-runs", response_model=list[EvalRunOut])
async def list_eval_runs(ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep),
                         dataset_id: str | None = Query(None, max_length=64), limit: int = Query(50, ge=1, le=200)):
    return [present_eval(e) for e in await EvaluationService(db).list_runs(ctx.workspace_id, dataset_id, limit)]


@router.post("/eval-runs", response_model=EvalRunOut, status_code=202)
async def create_eval_run(body: EvalRunCreate, ctx: Ctx = Depends(require("runs:create")), db=Depends(db_dep)):
    """Queues one agent run per dataset case; scores appear as the worker finishes them."""
    return present_eval(await EvaluationService(db).create_run(ctx.workspace_id, ctx.user_id, ctx.role, body))


@router.get("/eval-runs/compare", response_model=CompareOut)
async def compare_eval_runs(a: str = Query(..., max_length=64), b: str = Query(..., max_length=64),
                            ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return await EvaluationService(db).compare(ctx.workspace_id, a, b)


@router.get("/eval-runs/{eval_id}", response_model=EvalRunOut)
async def get_eval_run(eval_id: str, ctx: Ctx = Depends(require("agents:read")), db=Depends(db_dep)):
    return present_eval(await EvaluationService(db).get_run(ctx.workspace_id, eval_id))


@router.delete("/eval-runs/{eval_id}", status_code=204)
async def delete_eval_run(eval_id: str, ctx: Ctx = Depends(require("agents:write")), db=Depends(db_dep)):
    await EvaluationService(db).delete_run(ctx.workspace_id, ctx.user_id, eval_id)
