"""Domain exceptions mapped to a consistent JSON error envelope."""
from typing import Any


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class Unprocessable(AppError):
    status_code = 422
    code = "UNPROCESSABLE"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
