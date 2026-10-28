from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.client import ping

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready():
    db_ok = await ping()
    body = {"status": "ok" if db_ok else "degraded", "mongodb": "ok" if db_ok else "unreachable",
            "demo_mode": get_settings().demo_mode}
    return JSONResponse(body, status_code=200 if db_ok else 503)
