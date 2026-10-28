from datetime import datetime

from pydantic import EmailStr, Field, model_validator

from app.schemas.common import ApiModel, OutModel, Role


class RegisterRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=1, max_length=120)
    # Required unless invite_token is given (the invitee joins the inviting workspace).
    workspace_name: str | None = Field(default=None, min_length=1, max_length=120)
    invite_token: str | None = Field(default=None, min_length=10, max_length=200)

    @model_validator(mode="after")
    def _workspace_or_invite(self) -> "RegisterRequest":
        if not self.invite_token and not self.workspace_name:
            raise ValueError("workspace_name is required when registering without an invitation")
        return self


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class WorkspaceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class AuthConfigOut(OutModel):
    registration_open: bool
    demo_mode: bool


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(OutModel):
    id: str
    email: str
    name: str
    created_at: datetime


class MembershipOut(OutModel):
    workspace_id: str
    workspace_name: str
    role: Role


class MeOut(OutModel):
    user: UserOut
    memberships: list[MembershipOut]
    demo_mode: bool


class WorkspaceOut(OutModel):
    id: str
    name: str
    role: Role
    monthly_budget_usd: float | None
    created_at: datetime


class WorkspaceUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)


class MemberOut(OutModel):
    user_id: str
    email: str
    name: str
    role: Role
    joined_at: datetime


class MemberAdd(ApiModel):
    email: EmailStr
    role: Role


class MemberRoleUpdate(ApiModel):
    role: Role


class InvitationCreate(ApiModel):
    email: EmailStr
    role: Role


class InvitationOut(OutModel):
    id: str
    email: str
    role: Role
    invited_by: str
    created_at: datetime
    expires_at: datetime


class InvitationCreated(InvitationOut):
    token: str
    url: str


class InvitationInfo(OutModel):
    email: str
    role: Role
    workspace_name: str
    expires_at: datetime
    has_account: bool


class ApiKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    role: Role = "operator"
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(OutModel):
    id: str
    name: str
    role: Role
    prefix: str
    created_by: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str
