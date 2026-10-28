
from dataclasses import dataclass

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.core.exceptions import Forbidden, NotFound, RateLimited, Unauthorized
from app.db.client import get_db
from app.repositories.audit import RateLimitRepository
from app.repositories.identity import WorkspaceRepository
from app.services.auth import AuthService
from app.services.rbac import has_permission
from app.services.team import ApiKeyService


def db_dep() -> AsyncDatabase:
    return get_db()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, value = auth.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


async def current_user(request: Request, db: AsyncDatabase = Depends(db_dep)) -> dict:
    """Session cookie (browser) or workspace API key (``Authorization: Bearer orch_...``).

    An API key resolves to a synthetic principal bound to exactly one workspace and role."""
    bearer = bearer_token(request)
    if bearer:
        key = await ApiKeyService(db).resolve(bearer)
        if not key:
            raise Unauthorized("Invalid or revoked API key", code="INVALID_API_KEY")
        return {"_id": key["_id"], "email": f"{key['_id']}@api-key", "name": f"API key: {key['name']}",
                "created_at": key["created_at"], "_api_key": key}
    token = request.cookies.get(get_settings().session_cookie_name)
    user = await AuthService(db).resolve(token)
    if not user:
        raise Unauthorized("Authentication required")
    return user


@dataclass
class Ctx:
    user: dict
    workspace_id: str
    role: str

    @property
    def user_id(self) -> str:
        return self.user["_id"]


async def workspace_ctx(request: Request, user: dict = Depends(current_user),
                        db: AsyncDatabase = Depends(db_dep)) -> Ctx:
    repo = WorkspaceRepository(db)
    ws_id = request.headers.get("x-workspace-id") or request.query_params.get("workspace_id")
    key = user.get("_api_key")
    if key:
        if ws_id and ws_id != key["workspace_id"]:
            raise NotFound("Workspace not found", code="WORKSPACE_NOT_FOUND")
        return Ctx(user, key["workspace_id"], key["role"])
    if not ws_id:
        ms = await repo.memberships_for(user["_id"])
        if not ms:
            raise Forbidden("You are not a member of any workspace")
        return Ctx(user, ms[0]["workspace_id"], ms[0]["role"])
    m = await repo.membership(ws_id, user["_id"])
    if not m:
        # 404 rather than 403: do not confirm that another tenant's workspace exists.
        raise NotFound("Workspace not found", code="WORKSPACE_NOT_FOUND")
    return Ctx(user, ws_id, m["role"])


def require(permission: str):
    async def dep(ctx: Ctx = Depends(workspace_ctx)) -> Ctx:
        if not has_permission(ctx.role, permission):
            raise Forbidden(f"Role '{ctx.role}' lacks permission '{permission}'",
                            details={"permission": permission, "role": ctx.role})
        return ctx

    return dep


def rate_limit(name: str, per_minute: int):
    async def dep(request: Request, db: AsyncDatabase = Depends(db_dep)) -> None:
        key = f"{name}:{client_ip(request)}"
        if await RateLimitRepository(db).hit(key, 60) > per_minute:
            raise RateLimited("Too many requests; slow down", details={"limit_per_minute": per_minute})

    return dep
