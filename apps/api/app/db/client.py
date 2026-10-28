"""Async MongoDB access via PyMongo's native asyncio API (pymongo.AsyncMongoClient)."""
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncMongoClient(s.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=5000, appname="orchestrator")
    return _client


def get_db() -> AsyncDatabase:
    return get_client()[get_settings().mongodb_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except Exception:
        return False
