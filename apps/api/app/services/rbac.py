"""Role-based access control. Permissions are checked in FastAPI for every protected
operation (see app.api.deps.require). The UI only mirrors these for display."""
from typing import Literal

Permission = Literal[
    "workspace:read", "workspace:update", "members:read", "members:manage",
    "agents:read", "agents:write", "agents:publish",
    "providers:read", "providers:write",
    "runs:read", "runs:create", "runs:cancel",
    "audit:read", "usage:read", "api_keys:manage",
    "tools:read", "tools:write", "knowledge:read", "knowledge:write",
]

_VIEWER = {"workspace:read", "members:read", "agents:read", "providers:read", "runs:read", "usage:read",
           "tools:read", "knowledge:read"}
_OPERATOR = _VIEWER | {"runs:create", "runs:cancel"}
_DEVELOPER = _OPERATOR | {"agents:write", "agents:publish", "tools:write", "knowledge:write"}
_ADMIN = _DEVELOPER | {"providers:write", "members:manage", "workspace:update", "audit:read", "api_keys:manage"}
_OWNER = set(_ADMIN)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer": frozenset(_VIEWER),
    "operator": frozenset(_OPERATOR),
    "developer": frozenset(_DEVELOPER),
    "administrator": frozenset(_ADMIN),
    "owner": frozenset(_OWNER),
}

ROLE_RANK = {"viewer": 0, "operator": 1, "developer": 2, "administrator": 3, "owner": 4}


def has_permission(role: str, perm: str) -> bool:
    return perm in ROLE_PERMISSIONS.get(role, frozenset())
