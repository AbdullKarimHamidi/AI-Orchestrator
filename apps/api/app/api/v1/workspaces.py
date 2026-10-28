from fastapi import APIRouter, Depends, Query

from app.api.deps import Ctx, db_dep, require
from app.repositories.audit import AuditRepository
from app.repositories.identity import WorkspaceRepository
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.schemas.common import Page
from app.schemas.runs import DashboardOut
from app.services.runs import dashboard
from app.services.team import ApiKeyService, InvitationService, present_api_key, present_invitation
from app.services.workspaces import WorkspaceService

router = APIRouter(tags=["workspace"])


def _ws_out(ws: dict, role: str) -> dict:
    return {"id": ws["_id"], "name": ws["name"], "role": role,
            "monthly_budget_usd": (ws.get("settings") or {}).get("monthly_budget_usd"),
            "created_at": ws["created_at"]}


@router.get("/workspace", response_model=WorkspaceOut)
async def get_workspace(ctx: Ctx = Depends(require("workspace:read")), db=Depends(db_dep)):
    return _ws_out(await WorkspaceRepository(db).get(ctx.workspace_id), ctx.role)


@router.patch("/workspace", response_model=WorkspaceOut)
async def update_workspace(body: WorkspaceUpdate, ctx: Ctx = Depends(require("workspace:update")),
                           db=Depends(db_dep)):
    repo = WorkspaceRepository(db)
    fields = {}
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        fields["name"] = data["name"]
    if "monthly_budget_usd" in data:
        fields["settings.monthly_budget_usd"] = data["monthly_budget_usd"]
    if fields:
        await repo.update(ctx.workspace_id, fields)
        await AuditRepository(db).record(ctx.workspace_id, ctx.user_id, "workspace.update", "workspace",
                                         ctx.workspace_id, data)
    return _ws_out(await repo.get(ctx.workspace_id), ctx.role)


@router.get("/workspace/members", response_model=list[MemberOut])
async def list_members(ctx: Ctx = Depends(require("members:read")), db=Depends(db_dep)):
    return await WorkspaceService(db).members(ctx.workspace_id)


@router.post("/workspace/members", status_code=201, response_model=list[MemberOut])
async def add_member(body: MemberAdd, ctx: Ctx = Depends(require("members:manage")), db=Depends(db_dep)):
    svc = WorkspaceService(db)
    await svc.add_member(ctx.workspace_id, ctx.user, ctx.role, body.email, body.role)
    return await svc.members(ctx.workspace_id)


@router.patch("/workspace/members/{user_id}", response_model=list[MemberOut])
async def change_role(user_id: str, body: MemberRoleUpdate, ctx: Ctx = Depends(require("members:manage")),
                      db=Depends(db_dep)):
    svc = WorkspaceService(db)
    await svc.set_role(ctx.workspace_id, ctx.user, ctx.role, user_id, body.role)
    return await svc.members(ctx.workspace_id)


@router.delete("/workspace/members/{user_id}", status_code=204)
async def remove_member(user_id: str, ctx: Ctx = Depends(require("members:manage")), db=Depends(db_dep)):
    await WorkspaceService(db).remove(ctx.workspace_id, ctx.user, ctx.role, user_id)


@router.get("/audit-logs", response_model=Page[dict])
async def audit_logs(ctx: Ctx = Depends(require("audit:read")), db=Depends(db_dep),
                     limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                     action: str | None = Query(None, max_length=64)):
    f = {"action": action} if action else None
    items, total = await AuditRepository(db).list(ctx.workspace_id, f, limit=limit, offset=offset)
    return {"items": [{"id": i["_id"], "action": i["action"], "actor_id": i.get("actor_id"),
                       "target_type": i.get("target_type"), "target_id": i.get("target_id"),
                       "details": i.get("details", {}), "ip": i.get("ip"), "ts": i["ts"]} for i in items],
            "total": total, "limit": limit, "offset": offset}


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(ctx: Ctx = Depends(require("runs:read")), db=Depends(db_dep),
                        days: int = Query(7, ge=1, le=90)):
    return await dashboard(db, ctx.workspace_id, days)


@router.get("/rbac/roles", response_model=list[dict])
async def list_roles(_: Ctx = Depends(require("workspace:read"))):
    from app.services.rbac import ROLE_PERMISSIONS, ROLE_RANK

    return [{"role": r, "permissions": sorted(ROLE_PERMISSIONS[r])}
            for r in sorted(ROLE_PERMISSIONS, key=lambda r: -ROLE_RANK[r])]


@router.get("/workspace/invitations", response_model=list[InvitationOut])
async def list_invitations(ctx: Ctx = Depends(require("members:manage")), db=Depends(db_dep)):
    return [present_invitation(i) for i in await InvitationService(db).inv.pending(ctx.workspace_id)]


@router.post("/workspace/invitations", response_model=InvitationCreated, status_code=201)
async def create_invitation(body: InvitationCreate, ctx: Ctx = Depends(require("members:manage")),
                            db=Depends(db_dep)):
    """Returns a single-use invitation link (shown once). Share it with the invitee."""
    return await InvitationService(db).create(ctx.workspace_id, ctx.user_id, ctx.role, body.email, body.role)


@router.delete("/workspace/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: str, ctx: Ctx = Depends(require("members:manage")),
                            db=Depends(db_dep)):
    await InvitationService(db).revoke(ctx.workspace_id, ctx.user_id, invitation_id)


@router.get("/workspace/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(ctx: Ctx = Depends(require("api_keys:manage")), db=Depends(db_dep)):
    return [present_api_key(k) for k in await ApiKeyService(db).keys.active(ctx.workspace_id)]


@router.post("/workspace/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(body: ApiKeyCreate, ctx: Ctx = Depends(require("api_keys:manage")), db=Depends(db_dep)):
    """Returns the plaintext key once. Use it as `Authorization: Bearer <key>`."""
    return await ApiKeyService(db).create(ctx.workspace_id, ctx.user, ctx.role, body.name, body.role,
                                          body.expires_in_days)


@router.delete("/workspace/api-keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, ctx: Ctx = Depends(require("api_keys:manage")), db=Depends(db_dep)):
    await ApiKeyService(db).revoke(ctx.workspace_id, ctx.user_id, key_id)
