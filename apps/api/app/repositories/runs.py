"""Runs double as the durable job queue: a run in status 'queued' with available_at <= now
is claimable. Claims are atomic (find_one_and_update) and grant a time-bounded lease that
the worker must renew via heartbeat. Expired leases are recovered by any worker."""
from datetime import datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.repositories.base import ScopedRepository, now


class RunRepository(ScopedRepository):
    collection_name = "runs"

    async def insert(self, doc: dict) -> dict:
        await self.col.insert_one(doc)
        return doc

    async def insert_idempotent(self, doc: dict) -> tuple[dict, bool]:
        """Returns (run, created). Duplicate idempotency key returns the existing run."""
        try:
            await self.col.insert_one(doc)
            return doc, True
        except DuplicateKeyError:
            existing = await self.col.find_one({"workspace_id": doc["workspace_id"],
                                                "idempotency_key": doc["idempotency_key"]})
            if existing is None:
                raise
            return existing, False

    async def request_cancel(self, workspace_id: str, run_id: str) -> dict | None:
        """Sets cancel_requested; queued runs are cancelled immediately (no worker owns them)."""
        t = now()
        queued = await self.col.find_one_and_update(
            {"_id": run_id, "workspace_id": workspace_id, "status": "queued"},
            {"$set": {"status": "cancelled", "cancel_requested": True, "finished_at": t, "updated_at": t,
                      "error": {"code": "CANCELLED", "message": "Cancelled before execution started"}}},
            return_document=ReturnDocument.AFTER)
        if queued:
            return queued
        return await self.col.find_one_and_update(
            {"_id": run_id, "workspace_id": workspace_id, "status": {"$in": ["running", "waiting_for_approval"]}},
            {"$set": {"cancel_requested": True, "updated_at": t}}, return_document=ReturnDocument.AFTER)

    # ----- worker-side (unscoped by design: the worker serves all workspaces) -----
    async def claim(self, worker_id: str, lease_seconds: int) -> dict | None:
        t = now()
        return await self.col.find_one_and_update(
            {"status": "queued", "available_at": {"$lte": t}, "cancel_requested": False},
            {"$set": {"status": "running", "lease_owner": worker_id,
                      "lease_expires_at": t + timedelta(seconds=lease_seconds),
                      "started_at": t, "updated_at": t}, "$inc": {"attempt": 1}},
            sort=[("available_at", 1)], return_document=ReturnDocument.AFTER)

    async def heartbeat(self, run_id: str, worker_id: str, lease_seconds: int) -> dict | None:
        """Renews the lease only if this worker still owns it; returns the fresh run doc."""
        t = now()
        return await self.col.find_one_and_update(
            {"_id": run_id, "lease_owner": worker_id, "status": "running"},
            {"$set": {"lease_expires_at": t + timedelta(seconds=lease_seconds), "updated_at": t}},
            return_document=ReturnDocument.AFTER)

    async def finish(self, run_id: str, worker_id: str, fields: dict) -> bool:
        t = now()
        r = await self.col.update_one(
            {"_id": run_id, "lease_owner": worker_id, "status": "running"},
            {"$set": {**fields, "finished_at": t, "updated_at": t, "lease_owner": None, "lease_expires_at": None}})
        return r.modified_count == 1

    async def expired_leases(self, t: datetime) -> list[dict]:
        return [d async for d in self.col.find({"status": "running", "lease_expires_at": {"$lt": t}}).limit(50)]

    async def requeue_or_fail(self, run: dict, backoff_seconds: float) -> str | None:
        """Lease recovery. Re-queues if attempts remain; otherwise fails. Guarded by the
        observed lease so two recovering workers cannot both act on the same run."""
        t = now()
        guard = {"_id": run["_id"], "status": "running", "lease_owner": run.get("lease_owner"),
                 "lease_expires_at": run.get("lease_expires_at")}
        if run.get("cancel_requested"):
            fields = {"status": "cancelled", "finished_at": t,
                      "error": {"code": "CANCELLED", "message": "Cancelled (worker lost during cancellation)"}}
        elif run.get("deadline_at") and run["deadline_at"] <= t:
            fields = {"status": "timed_out", "finished_at": t,
                      "error": {"code": "TIMEOUT", "message": "Run deadline passed while worker was unavailable"}}
        elif run.get("attempt", 0) < run.get("max_attempts", 1):
            fields = {"status": "queued", "available_at": t + timedelta(seconds=backoff_seconds)}
        else:
            fields = {"status": "failed", "finished_at": t,
                      "error": {"code": "WORKER_LOST", "message": "Worker lease expired and no attempts remain"}}
        r = await self.col.update_one(guard, {"$set": {**fields, "updated_at": t, "lease_owner": None,
                                                       "lease_expires_at": None}})
        return fields["status"] if r.modified_count == 1 else None


class RunEventRepository:
    """Append-only event log per run with a strictly increasing seq (unique index)."""

    def __init__(self, db):
        self.col = db["run_events"]
        self.runs = db["runs"]

    async def append(self, run_id: str, workspace_id: str, type_: str, data: dict) -> int:
        counter = await self.runs.find_one_and_update({"_id": run_id}, {"$inc": {"event_seq": 1}},
                                                      projection={"event_seq": 1},
                                                      return_document=ReturnDocument.AFTER)
        seq = int(counter["event_seq"]) if counter else 0
        await self.col.insert_one({"run_id": run_id, "workspace_id": workspace_id, "seq": seq,
                                   "type": type_, "ts": now(), "data": data})
        return seq

    async def after(self, workspace_id: str, run_id: str, after_seq: int, limit: int = 500) -> list[dict]:
        return [d async for d in self.col.find({"run_id": run_id, "workspace_id": workspace_id,
                                                "seq": {"$gt": after_seq}}).sort("seq", 1).limit(limit)]
