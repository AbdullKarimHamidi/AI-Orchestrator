"""Background worker: `python -m app.workers.main`.

Durability model (MongoDB-backed queue; no Redis):
- Claim: atomic find_one_and_update queued->running with a lease (lease_owner, lease_expires_at).
- Heartbeat: every ~1s the supervisor renews the lease and re-reads the run. That same read
  is the cancellation watcher (cancel_requested) and deadline check (timed_out).
- Crash recovery: any worker re-queues runs whose lease expired (bounded by max_attempts),
  or marks them failed/cancelled/timed_out. API restarts do not affect runs.
- Mongo outage: claim/heartbeat raise; the loop backs off and retries. A run whose lease
  cannot be renewed is eventually recovered by lease expiry.
- SIGTERM: stop claiming, cancel in-flight executions, release them back to the queue.
"""
import asyncio
import contextlib
import logging
import os
import signal
import socket
from datetime import timedelta

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.logging import configure_logging, correlation_id, redact
from app.core.security import get_cipher
from app.db.client import close_client, get_db
from app.db.indexes import ensure_schema
from app.orchestration.agent_executor import AgentExecutor, RunFailure
from app.orchestration.workflow_executor import WorkflowExecutor
from app.repositories.base import now
from app.repositories.knowledge import DocumentRepository
from app.repositories.runs import RunEventRepository, RunRepository
from app.services.knowledge import KnowledgeService

INGEST_LEASE_SECONDS = 600

log = logging.getLogger("worker")

# Liveness file touched on every loop iteration; the container healthcheck reads its mtime.
HEARTBEAT_FILE = os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker-heartbeat")  # noqa: S108


def touch_heartbeat() -> None:
    with contextlib.suppress(OSError):
        with open(HEARTBEAT_FILE, "a"):
            os.utime(HEARTBEAT_FILE)


class Worker:
    def __init__(self, db=None, worker_id: str | None = None, *, heartbeat_interval: float = 1.0):
        self.s = get_settings()
        self.db = db if db is not None else get_db()
        self.id = worker_id or f"wrk-{socket.gethostname()}-{os.getpid()}-{new_id('w')[-6:]}"
        self.runs = RunRepository(self.db)
        self.events = RunEventRepository(self.db)
        self.executor = AgentExecutor(self.db)
        self.workflow_executor = WorkflowExecutor(self.db)
        self.heartbeat_interval = heartbeat_interval
        self.inflight: dict[str, asyncio.Task] = {}
        self.stopping = asyncio.Event()

    async def process(self, run: dict) -> str:
        """Supervises one claimed run until a terminal state. Returns the final status."""
        rid, ws = run["_id"], run["workspace_id"]
        correlation_id.set(rid)
        deadline = now() + timedelta(seconds=run["timeout_seconds"])
        await self.db["runs"].update_one({"_id": rid, "lease_owner": self.id}, {"$set": {"deadline_at": deadline}})
        await self.events.append(rid, ws, "run.started", {"attempt": run["attempt"], "worker": self.id})
        executor = self.workflow_executor if run.get("kind") == "workflow" else self.executor
        task = asyncio.create_task(executor.execute(run))
        final: dict | None = None
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=self.heartbeat_interval)
                if done:
                    break
                fresh = await self.runs.heartbeat(rid, self.id, self.s.worker_lease_seconds)
                if fresh is None:  # lease lost (recovered elsewhere): stop without writing
                    task.cancel()
                    log.warning("lease lost", extra={"extra_fields": {"run_id": rid}})
                    return "lease_lost"
                if fresh.get("cancel_requested"):
                    task.cancel()
                    final = {"status": "cancelled",
                             "error": {"code": "CANCELLED", "message": "Cancelled by user during execution"}}
                    break
                if now() >= deadline:
                    task.cancel()
                    final = {"status": "timed_out", "error": {
                        "code": "TIMEOUT", "message": f"Run exceeded {run['timeout_seconds']}s timeout"}}
                    break
            if final is None:
                try:
                    res = task.result()
                    final = {"status": "completed", "output": res.output, "usage": res.usage, "demo": res.demo}
                except RunFailure as f:
                    final = {"status": "failed", "error": {"code": f.code, "message": f.message}}
                except asyncio.CancelledError:
                    final = {"status": "cancelled", "error": {"code": "CANCELLED", "message": "Execution cancelled"}}
                except Exception:  # unexpected bug: fail closed, details only in server logs
                    log.exception("executor crashed", extra={"extra_fields": {"run_id": rid}})
                    final = {"status": "failed", "error": {"code": "INTERNAL", "message": "Internal executor error"}}
            else:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if "usage" not in final:
                final["usage"] = await self._usage_total(rid)
            if final.get("error"):
                final["error"] = redact(final["error"])  # provider messages can echo credentials
            if await self.runs.finish(rid, self.id, final):
                await self.events.append(rid, ws, f"run.{final['status']}",
                                         {"error": final.get("error"), "usage": final["usage"]})
            return final["status"]
        finally:
            if not task.done():
                task.cancel()

    async def _usage_total(self, run_id: str) -> dict:
        tot = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        async for u in self.db["usage_records"].find({"run_id": run_id}):
            tot["input_tokens"] += u.get("input_tokens", 0)
            tot["output_tokens"] += u.get("output_tokens", 0)
            tot["cost_usd"] = round(tot["cost_usd"] + u.get("cost_usd", 0.0), 8)
        return tot

    async def recover_expired(self) -> int:
        n = 0
        for run in await self.runs.expired_leases(now()):
            status = await self.runs.requeue_or_fail(run, backoff_seconds=2 ** max(0, run.get("attempt", 1) - 1))
            if status:
                n += 1
                await self.events.append(run["_id"], run["workspace_id"], "run.lease_expired",
                                         {"previous_worker": run.get("lease_owner"), "new_status": status})
        return n

    async def release_inflight(self) -> None:
        for rid, task in list(self.inflight.items()):
            task.cancel()
            await self.db["runs"].update_one({"_id": rid, "lease_owner": self.id, "status": "running"},
                                             {"$set": {"status": "queued", "lease_owner": None,
                                                       "lease_expires_at": None, "available_at": now()},
                                              "$inc": {"attempt": -1}})

    async def ingest_one(self) -> bool:
        """Claims and processes one queued knowledge document. Returns False when the queue is empty."""
        docs = DocumentRepository(self.db)
        d = await docs.claim(self.id, INGEST_LEASE_SECONDS)
        if not d:
            return False
        correlation_id.set(d["_id"])
        try:
            fields = await KnowledgeService(self.db).ingest(d)
        except Exception:  # unexpected bug: fail the document, keep the worker alive
            log.exception("ingestion crashed", extra={"extra_fields": {"doc_id": d["_id"]}})
            fields = {"status": "failed", "error": "internal ingestion error"}
        await docs.finish(d["_id"], self.id, fields)
        log.info("document ingested", extra={"extra_fields": {"doc_id": d["_id"], "status": fields["status"]}})
        return True

    async def ingest_forever(self) -> None:
        """Knowledge ingestion runs beside run execution, one document at a time per worker."""
        docs = DocumentRepository(self.db)
        last_recovery = 0.0
        loop = asyncio.get_running_loop()
        while not self.stopping.is_set():
            try:
                if loop.time() - last_recovery > 60:
                    await docs.recover_expired(now())
                    last_recovery = loop.time()
                if await self.ingest_one():
                    continue
            except Exception:
                log.exception("ingestion loop error; backing off")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=1.0)

    async def run_forever(self) -> None:
        log.info("worker started", extra={"extra_fields": {"worker_id": self.id}})
        ingest = asyncio.create_task(self.ingest_forever())
        last_recovery = 0.0
        loop = asyncio.get_running_loop()
        backoff = self.s.worker_poll_interval_seconds
        while not self.stopping.is_set():
            touch_heartbeat()
            try:
                if loop.time() - last_recovery > self.s.worker_lease_seconds / 2:
                    await self.recover_expired()
                    last_recovery = loop.time()
                claimed = False
                while len(self.inflight) < self.s.worker_concurrency:
                    run = await self.runs.claim(self.id, self.s.worker_lease_seconds)
                    if not run:
                        break
                    claimed = True
                    t = asyncio.create_task(self.process(run))
                    self.inflight[run["_id"]] = t
                    t.add_done_callback(lambda _t, rid=run["_id"]: self.inflight.pop(rid, None))
                backoff = self.s.worker_poll_interval_seconds
                if not claimed:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self.stopping.wait(), timeout=backoff)
            except Exception:
                log.exception("worker loop error (database unavailable?); backing off")
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.stopping.wait(), timeout=backoff)
                backoff = min(backoff * 2, 15)
        await self.release_inflight()
        ingest.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ingest
        log.info("worker stopped")


async def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    s.validate_for_runtime()
    # Fail fast on malformed keys; warn on ephemeral ones (API and worker would not share them).
    if get_cipher().ephemeral:
        log.warning("ENCRYPTION_KEYS not set: the worker cannot decrypt provider keys stored by the API")
    await ensure_schema(get_db())
    w = Worker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # Windows: no add_signal_handler
            loop.add_signal_handler(sig, w.stopping.set)
    try:
        await w.run_forever()
    finally:
        await close_client()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
