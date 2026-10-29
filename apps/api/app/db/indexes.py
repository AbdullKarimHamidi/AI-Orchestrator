"""Collection validators and indexes. Idempotent; run at API/worker startup.

Validators enforce the minimum structure (required fields and types). Pydantic models
in app.schemas enforce full business validation before writes. Validation level is
"moderate" so legacy documents can be migrated without blocking updates.
"""
import logging

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import CollectionInvalid

from app.core.config import get_settings

log = logging.getLogger(__name__)

_STR = {"bsonType": "string"}
_DATE = {"bsonType": "date"}


def _schema(required: list[str], props: dict) -> dict:
    return {"$jsonSchema": {"bsonType": "object", "required": required, "properties": props}}


VALIDATORS: dict[str, dict] = {
    "projects": _schema(["_id", "workspace_id", "name", "idea", "status", "revision", "created_at"],
                     {"_id": _STR, "workspace_id": _STR, "name": _STR, "idea": _STR,
                      "status": {"enum": ["planning", "ready", "in_progress", "blocked", "completed", "archived"]},
                      "revision": {"bsonType": ["int", "long"]}}),
    "users": _schema(["_id", "email", "password_hash", "created_at"],
                     {"_id": _STR, "email": _STR, "password_hash": _STR, "created_at": _DATE}),
    "workspaces": _schema(["_id", "name", "owner_id", "created_at"],
                          {"_id": _STR, "name": _STR, "owner_id": _STR}),
    "workspace_members": _schema(["workspace_id", "user_id", "role"], {
        "workspace_id": _STR, "user_id": _STR,
        "role": {"enum": ["owner", "administrator", "developer", "operator", "viewer"]}}),
    "sessions": _schema(["_id", "user_id", "expires_at"], {"_id": _STR, "user_id": _STR, "expires_at": _DATE}),
    "agents": _schema(["_id", "workspace_id", "name", "status", "draft", "revision"], {
        "_id": _STR, "workspace_id": _STR, "name": _STR,
        "status": {"enum": ["draft", "published", "paused", "retired"]},
        "revision": {"bsonType": ["int", "long"]}}),
    "agent_versions": _schema(["_id", "workspace_id", "agent_id", "version", "config", "config_hash"], {
        "workspace_id": _STR, "agent_id": _STR, "version": {"bsonType": ["int", "long"]}}),
    "model_providers": _schema(["_id", "workspace_id", "kind", "name"], {
        "workspace_id": _STR, "kind": {"enum": ["openai", "anthropic", "gemini", "openai_compatible", "demo"]}}),
    "runs": _schema(["_id", "workspace_id", "status", "created_at"], {
        "workspace_id": _STR,
        "status": {"enum": ["queued", "running", "waiting_for_approval", "completed", "failed",
                            "cancelled", "timed_out"]}}),
    "run_events": _schema(["run_id", "workspace_id", "seq", "type", "ts"], {
        "run_id": _STR, "workspace_id": _STR, "seq": {"bsonType": ["int", "long"]}, "type": _STR, "ts": _DATE}),
    "audit_logs": _schema(["workspace_id", "action", "ts"], {"action": _STR, "ts": _DATE}),
    "usage_records": _schema(["workspace_id", "run_id", "ts"], {"workspace_id": _STR, "ts": _DATE}),
}


def index_plan() -> dict[str, list[IndexModel]]:
    s = get_settings()
    return {
        "users": [IndexModel([("email", ASCENDING)], unique=True)],
        "sessions": [IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
                     IndexModel([("user_id", ASCENDING)])],
        "workspace_members": [IndexModel([("workspace_id", ASCENDING), ("user_id", ASCENDING)], unique=True),
                              IndexModel([("user_id", ASCENDING)])],
        "agents": [IndexModel([("workspace_id", ASCENDING), ("updated_at", DESCENDING)]),
                   IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                              partialFilterExpression={"deleted": False})],
        "agent_versions": [IndexModel([("agent_id", ASCENDING), ("version", DESCENDING)], unique=True),
                           IndexModel([("workspace_id", ASCENDING)])],
        "model_providers": [IndexModel([("workspace_id", ASCENDING), ("name", ASCENDING)], unique=True)],
        "runs": [IndexModel([("workspace_id", ASCENDING), ("created_at", DESCENDING)]),
                 IndexModel([("workspace_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]),
                 IndexModel([("status", ASCENDING), ("available_at", ASCENDING)]),  # worker claim
                 IndexModel([("status", ASCENDING), ("lease_expires_at", ASCENDING)]),  # lease recovery
                 IndexModel([("workspace_id", ASCENDING), ("workflow_id", ASCENDING), ("created_at", DESCENDING)],
                            partialFilterExpression={"workflow_id": {"$type": "string"}}),
                 IndexModel([("eval_run_id", ASCENDING)], partialFilterExpression={"eval_run_id": {"$type": "string"}}),
                 IndexModel([("workspace_id", ASCENDING), ("idempotency_key", ASCENDING)], unique=True,
                            partialFilterExpression={"idempotency_key": {"$type": "string"}})],
        "run_events": [IndexModel([("run_id", ASCENDING), ("seq", ASCENDING)], unique=True),
                       IndexModel([("ts", ASCENDING)], expireAfterSeconds=s.run_events_retention_days * 86400)],
        "audit_logs": [IndexModel([("workspace_id", ASCENDING), ("ts", DESCENDING)]),
                       IndexModel([("ts", ASCENDING)], expireAfterSeconds=s.audit_retention_days * 86400)],
        "usage_records": [IndexModel([("workspace_id", ASCENDING), ("ts", DESCENDING)]),
                          IndexModel([("run_id", ASCENDING)])],
        "rate_limits": [IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0)],
        "invitations": [IndexModel([("token_hash", ASCENDING)], unique=True),
                        IndexModel([("workspace_id", ASCENDING), ("status", ASCENDING)])],
        "tools": [IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                             partialFilterExpression={"deleted": False})],
        "knowledge_bases": [IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                                       partialFilterExpression={"deleted": False})],
        "documents": [IndexModel([("workspace_id", ASCENDING), ("kb_id", ASCENDING), ("created_at", DESCENDING)]),
                      IndexModel([("workspace_id", ASCENDING), ("created_at", DESCENDING)]),
                      IndexModel([("status", ASCENDING), ("created_at", ASCENDING)]),
                      IndexModel([("status", ASCENDING), ("lease_expires_at", ASCENDING)])],
        "chunks": [IndexModel([("workspace_id", ASCENDING), ("kb_id", ASCENDING)]),
                   IndexModel([("workspace_id", ASCENDING), ("doc_id", ASCENDING)])],
        "projects": [
            IndexModel([("workspace_id", ASCENDING), ("updated_at", DESCENDING)]),
            IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                       partialFilterExpression={"deleted": False}),
        ],
        "workflows": [IndexModel([("workspace_id", ASCENDING), ("updated_at", DESCENDING)]),
                      IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                                 partialFilterExpression={"deleted": False})],
        "workflow_versions": [IndexModel([("workflow_id", ASCENDING), ("version", DESCENDING)], unique=True),
                              IndexModel([("workspace_id", ASCENDING)])],
        "eval_datasets": [IndexModel([("workspace_id", ASCENDING), ("name_lower", ASCENDING)], unique=True,
                                     partialFilterExpression={"deleted": False})],
        "eval_runs": [IndexModel([("workspace_id", ASCENDING), ("created_at", DESCENDING)])],
        "memories": [IndexModel([("workspace_id", ASCENDING), ("agent_id", ASCENDING), ("scope", ASCENDING),
                                 ("created_at", DESCENDING)]),
                     IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0)],
        "api_keys": [IndexModel([("key_hash", ASCENDING)], unique=True),
                     IndexModel([("workspace_id", ASCENDING), ("revoked", ASCENDING)])],
    }


async def ensure_schema(db: AsyncDatabase) -> None:
    existing = set(await db.list_collection_names())
    for name, validator in VALIDATORS.items():
        if name not in existing:
            try:
                await db.create_collection(name, validator=validator, validationLevel="moderate")
            except CollectionInvalid:
                pass
        else:
            await db.command({"collMod": name, "validator": validator, "validationLevel": "moderate"})
    for name, models in index_plan().items():
        await db[name].create_indexes(models)
    log.info("schema ensured")
