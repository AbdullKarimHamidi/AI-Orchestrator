from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.schemas.billing import AgentBreakdownRow, BillingOut, PlanChange, StatementOut, TimeseriesRow
from app.services.analytics import breakdown, timeseries
from app.services.billing import BillingService

router = APIRouter(tags=["billing"])


@router.get("/billing", response_model=BillingOut)
async def get_billing(ctx: Ctx = Depends(require("usage:read")), db=Depends(db_dep)):
    return await BillingService(db).overview(ctx.workspace_id)


@router.post("/billing/plan", response_model=BillingOut)
async def change_plan(body: PlanChange, ctx: Ctx = Depends(require("workspace:update")), db=Depends(db_dep)):
    return await BillingService(db).change_plan(ctx.workspace_id, ctx.user_id, body.plan)


@router.get("/billing/statements", response_model=list[StatementOut])
async def statements(ctx: Ctx = Depends(require("usage:read")), db=Depends(db_dep),
                     months: int = Query(6, ge=1, le=24)):
    return await BillingService(db).statements(ctx.workspace_id, months)


@router.get("/analytics/timeseries", response_model=list[TimeseriesRow])
async def analytics_timeseries(ctx: Ctx = Depends(require("usage:read")), db=Depends(db_dep),
                               days: int = Query(30, ge=1, le=90)):
    return await timeseries(db, ctx.workspace_id, days)


@router.get("/analytics/breakdown", response_model=list[AgentBreakdownRow])
async def analytics_breakdown(ctx: Ctx = Depends(require("usage:read")), db=Depends(db_dep),
                              days: int = Query(30, ge=1, le=90)):
    return await breakdown(db, ctx.workspace_id, days)
