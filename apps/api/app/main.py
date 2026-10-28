"""FastAPI application factory. Handlers are thin; logic lives in app.services."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, correlation_id
from app.core.security import get_cipher
from app.db.client import close_client, get_db
from app.db.indexes import ensure_schema
from app.middleware.core import BodySizeLimitMiddleware, CSRFMiddleware, RequestContextMiddleware

log = logging.getLogger("api")


def _err(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {},
                                   "correlation_id": correlation_id.get()}}, status_code=status)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    s.validate_for_runtime()
    if get_cipher().ephemeral:
        log.warning("ENCRYPTION_KEYS not set: using an ephemeral key; stored provider keys will not survive restart")
    try:
        await ensure_schema(get_db())
    except Exception:
        # Start anyway so /health/ready can report the outage; requests fail with 503.
        log.exception("could not initialize MongoDB schema at startup")
    yield
    await close_client()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="AI Orchestration Platform API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return _err(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errs = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _err(422, "VALIDATION_ERROR", "Request validation failed", {"errors": errs})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return _err(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        from pymongo.errors import PyMongoError

        if isinstance(exc, PyMongoError):
            log.exception("database error")
            return _err(503, "DATABASE_UNAVAILABLE", "The database is temporarily unavailable")
        log.exception("unhandled error")
        return _err(500, "INTERNAL", "Internal server error")

    app.include_router(api_router)
    # Order: outermost added last. Context -> size limit -> CSRF -> CORS -> app.
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Workspace-Id",
                                      "Idempotency-Key", "X-Request-Id", "Last-Event-ID"])
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    return app


app = create_app()
