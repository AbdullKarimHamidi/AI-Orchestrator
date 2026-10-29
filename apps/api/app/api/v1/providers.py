from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.repositories.audit import UsageRepository
from app.schemas.providers import (
    ConnectionTestOut,
    ModelTestOut,
    ModelTestRequest,
    PresetAdd,
    PresetOut,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)
from app.services.providers import ProviderService, present

router = APIRouter(prefix="/model-providers", tags=["models"])


@router.get("", response_model=list[ProviderOut])
async def list_providers(ctx: Ctx = Depends(require("providers:read")), db=Depends(db_dep)):
    return [present(p) for p in await ProviderService(db).list(ctx.workspace_id)]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(body: ProviderCreate, ctx: Ctx = Depends(require("providers:write")), db=Depends(db_dep)):
    return present(await ProviderService(db).create(ctx.workspace_id, ctx.user_id, body))


@router.get("/presets", response_model=list[PresetOut])
async def list_presets(ctx: Ctx = Depends(require("providers:read")), db=Depends(db_dep)):
    """Free AI APIs that can be connected in one step, and whether each is set up already."""
    return await ProviderService(db).presets(ctx.workspace_id)


@router.post("/presets/{preset_id}", response_model=ProviderOut, status_code=201)
async def add_preset(preset_id: str, body: PresetAdd, ctx: Ctx = Depends(require("providers:write")),
                     db=Depends(db_dep)):
    return present(await ProviderService(db).add_preset(ctx.workspace_id, ctx.user_id, preset_id, body.api_key,
                                                        str(body.base_url) if body.base_url else None))


@router.get("/usage", response_model=list[dict])
async def provider_usage(ctx: Ctx = Depends(require("usage:read")), db=Depends(db_dep),
                         days: int = Query(30, ge=1, le=90)):
    from datetime import timedelta

    from app.repositories.base import now

    rows = await UsageRepository(db).col.aggregate([
        {"$match": {"workspace_id": ctx.workspace_id, "ts": {"$gte": now() - timedelta(days=days)}}},
        {"$group": {"_id": {"provider_id": "$provider_id", "model": "$model"}, "calls": {"$sum": 1},
                    "errors": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
                    "input_tokens": {"$sum": "$input_tokens"}, "output_tokens": {"$sum": "$output_tokens"},
                    "cost_usd": {"$sum": "$cost_usd"}, "avg_latency_ms": {"$avg": "$latency_ms"},
                    "unpriced": {"$sum": {"$cond": ["$priced", 0, 1]}}}},
        {"$sort": {"calls": -1}}])
    return [{**r["_id"], **{k: v for k, v in r.items() if k != "_id"}} async for r in rows]


@router.post("/{provider_id}/test-model", response_model=ModelTestOut)
async def test_provider_model(provider_id: str, body: ModelTestRequest,
                              ctx: Ctx = Depends(require("providers:write")), db=Depends(db_dep)):
    return await ProviderService(db).test_model(ctx.workspace_id, ctx.user_id, provider_id, body.model)


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(provider_id: str, ctx: Ctx = Depends(require("providers:read")), db=Depends(db_dep)):
    return present(await ProviderService(db).get(ctx.workspace_id, provider_id))


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdate, ctx: Ctx = Depends(require("providers:write")),
                          db=Depends(db_dep)):
    return present(await ProviderService(db).update(ctx.workspace_id, ctx.user_id, provider_id, body))


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, ctx: Ctx = Depends(require("providers:write")), db=Depends(db_dep)):
    await ProviderService(db).delete(ctx.workspace_id, ctx.user_id, provider_id)


@router.post("/{provider_id}/test", response_model=ConnectionTestOut)
async def test_provider(provider_id: str, ctx: Ctx = Depends(require("providers:write")), db=Depends(db_dep)):
    return await ProviderService(db).test_connection(ctx.workspace_id, ctx.user_id, provider_id)
