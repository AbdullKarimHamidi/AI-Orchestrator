import secrets

from fastapi import APIRouter, Depends, Request, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import client_ip, current_user, db_dep, rate_limit
from app.core.config import get_settings
from app.core.exceptions import Forbidden
from app.repositories.identity import WorkspaceRepository
from app.schemas.auth import (
    AuthConfigOut,
    InvitationInfo,
    LoginRequest,
    MeOut,
    PasswordChange,
    RegisterRequest,
    WorkspaceCreate,
)
from app.services.auth import AuthService
from app.services.providers import ProviderService
from app.services.team import InvitationService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookies(resp: Response, token: str) -> None:
    s = get_settings()
    max_age = s.session_ttl_hours * 3600
    resp.set_cookie(s.session_cookie_name, token, max_age=max_age, httponly=True, secure=s.cookie_secure,
                    samesite="lax", path="/")
    # Readable by JS on purpose (double-submit CSRF); carries no authority by itself.
    resp.set_cookie(s.csrf_cookie_name, secrets.token_urlsafe(24), max_age=max_age, httponly=False,
                    secure=s.cookie_secure, samesite="lax", path="/")


async def _me(db: AsyncDatabase, user: dict) -> dict:
    repo = WorkspaceRepository(db)
    out = []
    for m in await repo.memberships_for(user["_id"]):
        ws = await repo.get(m["workspace_id"])
        if ws:
            out.append({"workspace_id": ws["_id"], "workspace_name": ws["name"], "role": m["role"]})
    return {"user": {"id": user["_id"], "email": user["email"], "name": user["name"],
                     "created_at": user["created_at"]}, "memberships": out, "demo_mode": get_settings().demo_mode}


def _session_only(user: dict) -> dict:
    if user.get("_api_key"):
        raise Forbidden("This endpoint requires a signed-in user, not an API key", code="API_KEY_FORBIDDEN")
    return user


@router.get("/config", response_model=AuthConfigOut)
async def auth_config(db=Depends(db_dep)):
    """Public: lets the sign-up page know whether self-service registration is open."""
    return {"registration_open": await AuthService(db).registration_open(), "demo_mode": get_settings().demo_mode}


@router.post("/register", response_model=MeOut, status_code=201)
async def register(body: RegisterRequest, request: Request, response: Response, db=Depends(db_dep)):
    await rate_limit("register", get_settings().register_rate_limit_per_minute)(request, db)
    user, token = await AuthService(db).register(body, client_ip(request))
    for m in await WorkspaceRepository(db).memberships_for(user["_id"]):
        await ProviderService(db).ensure_demo(m["workspace_id"])
    _set_cookies(response, token)
    return await _me(db, user)


@router.post("/login", response_model=MeOut)
async def login(body: LoginRequest, request: Request, response: Response, db=Depends(db_dep)):
    await rate_limit(f"login:{body.email.lower()}", get_settings().login_rate_limit_per_minute)(request, db)
    user, token = await AuthService(db).login(body, client_ip(request))
    _set_cookies(response, token)
    return await _me(db, user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db=Depends(db_dep)):
    s = get_settings()
    token = request.cookies.get(s.session_cookie_name)
    if token:
        await AuthService(db).logout(token)
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")


@router.get("/me", response_model=MeOut)
async def me(user=Depends(current_user), db=Depends(db_dep)):
    return await _me(db, user)


@router.post("/password", status_code=204)
async def change_password(body: PasswordChange, request: Request, user=Depends(current_user), db=Depends(db_dep)):
    """Changes the password and signs out all of this user's other sessions."""
    await AuthService(db).change_password(_session_only(user), body,
                                          request.cookies.get(get_settings().session_cookie_name))


@router.post("/workspaces", response_model=MeOut, status_code=201)
async def create_workspace(body: WorkspaceCreate, user=Depends(current_user), db=Depends(db_dep)):
    """Creates an additional workspace owned by the signed-in user."""
    ws = await AuthService(db).create_workspace(_session_only(user), body.name)
    await ProviderService(db).ensure_demo(ws["_id"])
    return await _me(db, user)


@router.get("/invitations/{token}", response_model=InvitationInfo)
async def invitation_info(token: str, request: Request, db=Depends(db_dep)):
    """Public: what an invitation link grants (no secrets; the token itself is the credential)."""
    await rate_limit("invitation", 60)(request, db)
    return await InvitationService(db).describe(token)


@router.post("/invitations/{token}/accept", response_model=MeOut)
async def accept_invitation(token: str, user=Depends(current_user), db=Depends(db_dep)):
    inv = await InvitationService(db).accept(token, _session_only(user))
    await ProviderService(db).ensure_demo(inv["workspace_id"])
    return await _me(db, user)
