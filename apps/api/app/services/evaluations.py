"""Offline evaluations: datasets of cases, evaluation runs, scoring and comparison.

An evaluation run queues one ordinary agent run per case (tagged with ``eval_run_id``), so cases
execute in the worker with the same budget checks, fallbacks, tools, knowledge and usage records as
production traffic. Scoring is deterministic and happens when results are read: once every case
run is terminal the evaluation is marked completed and its scores are frozen.
"""
import re

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.orchestration.agent_executor import _extract_json
from app.repositories.agents import AgentRepository
from app.repositories.audit import AuditRepository
from app.repositories.base import ScopedRepository, now
from app.schemas.evaluations import DatasetCreate, DatasetUpdate, EvalRunCreate
from app.schemas.runs import TERMINAL, RunCreate
from app.services.runs import RunService


class DatasetRepository(ScopedRepository):
    collection_name = "eval_datasets"


class EvalRunRepository(ScopedRepository):
    collection_name = "eval_runs"


def score(scorer: dict, output: str, expected: str) -> tuple[bool, str]:
    """Returns (passed, reason)."""
    kind = scorer.get("type", "contains")
    cs = bool(scorer.get("case_sensitive"))
    a, b = (output, expected) if cs else (output.lower(), expected.lower())
    if kind == "exact":
        ok = a.strip() == b.strip()
        return ok, "output equals expected" if ok else "output differs from expected"
    if kind == "contains":
        ok = b.strip() in a
        return ok, "expected text found in output" if ok else "expected text not found in output"
    if kind == "not_contains":
        ok = b.strip() not in a
        return ok, "forbidden text absent" if ok else "forbidden text present in output"
    if kind == "regex":
        try:
            ok = re.search(expected, output, 0 if cs else re.IGNORECASE) is not None
        except re.error as exc:
            return False, f"invalid regular expression: {exc}"
        return ok, "pattern matched" if ok else "pattern did not match"
    if kind == "json_valid":
        try:
            _extract_json(output)
            return True, "output contains valid JSON"
        except ValueError as exc:
            return False, f"no valid JSON: {exc}"
    if kind == "not_empty":
        ok = bool(output.strip())
        return ok, "output is not empty" if ok else "output is empty"
    return False, f"unknown scorer {kind}"


def present_dataset(d: dict) -> dict:
    return {**d, "id": d["_id"], "case_count": len(d.get("cases") or [])}


def _normalize_cases(cases: list) -> list[dict]:
    out, seen = [], set()
    for i, c in enumerate(cases):
        cid = (c.id or "").strip() or f"case_{i + 1}"
        while cid in seen:
            cid = f"{cid}_{i + 1}"
        seen.add(cid)
        out.append({"id": cid, "input": c.input, "expected": c.expected, "variables": c.variables})
    return out


class EvaluationService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.datasets = DatasetRepository(db)
        self.evals = EvalRunRepository(db)
        self.agents = AgentRepository(db)
        self.runs = RunService(db)
        self.audit = AuditRepository(db)

    # ----- datasets -----
    async def get_dataset(self, ws_id: str, ds_id: str) -> dict:
        d = await self.datasets.col.find_one({"_id": ds_id, "workspace_id": ws_id, "deleted": False})
        if not d:
            raise NotFound("Dataset not found")
        return d

    async def list_datasets(self, ws_id: str) -> list[dict]:
        items, _ = await self.datasets.list(ws_id, {"deleted": False}, sort=[("updated_at", -1)], limit=200)
        return items

    async def create_dataset(self, ws_id: str, user_id: str, req: DatasetCreate) -> dict:
        t = now()
        doc = {"_id": new_id("eds"), "workspace_id": ws_id, "name": req.name, "name_lower": req.name.lower(),
               "description": req.description, "cases": _normalize_cases(req.cases), "deleted": False,
               "created_by": user_id, "created_at": t, "updated_at": t}
        try:
            await self.datasets.col.insert_one(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A dataset with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "dataset.create", "dataset", doc["_id"], {"cases": len(doc["cases"])})
        return doc

    async def update_dataset(self, ws_id: str, user_id: str, ds_id: str, req: DatasetUpdate) -> dict:
        await self.get_dataset(ws_id, ds_id)
        fields: dict = {"updated_at": now()}
        if req.name is not None:
            fields |= {"name": req.name, "name_lower": req.name.lower()}
        if req.description is not None:
            fields["description"] = req.description
        if req.cases is not None:
            fields["cases"] = _normalize_cases(req.cases)
        try:
            await self.datasets.col.update_one({"_id": ds_id, "workspace_id": ws_id}, {"$set": fields})
        except DuplicateKeyError as exc:
            raise Conflict("A dataset with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "dataset.update", "dataset", ds_id,
                                {"fields": sorted(k for k in fields if k != "updated_at")})
        return await self.get_dataset(ws_id, ds_id)

    async def delete_dataset(self, ws_id: str, user_id: str, ds_id: str) -> None:
        await self.get_dataset(ws_id, ds_id)
        await self.datasets.col.update_one({"_id": ds_id, "workspace_id": ws_id},
                                           {"$set": {"deleted": True, "name_lower": f"{ds_id}:deleted"}})
        await self.audit.record(ws_id, user_id, "dataset.delete", "dataset", ds_id)

    # ----- evaluation runs -----
    async def create_run(self, ws_id: str, user_id: str, role: str, req: EvalRunCreate) -> dict:
        ds = await self.get_dataset(ws_id, req.dataset_id)
        if not ds["cases"]:
            raise Unprocessable("The dataset has no cases", code="DATASET_EMPTY")
        agent = await self.agents.get(ws_id, req.agent_id)
        if not agent:
            raise NotFound("Agent not found")
        eval_id = new_id("evr")
        items = []
        version = None
        for c in ds["cases"]:
            run_input = {"message": c["input"]}
            if c.get("variables"):
                run_input["variables"] = c["variables"]
            run, _ = await self.runs.create(ws_id, user_id, role,
                                            RunCreate(agent_id=agent["_id"], input=run_input, source=req.source),
                                            None, extra={"eval_run_id": eval_id})
            version = run.get("agent_version")
            items.append({"case_id": c["id"], "input": c["input"], "expected": c["expected"], "run_id": run["_id"]})
        t = now()
        doc = {"_id": eval_id, "workspace_id": ws_id,
               "name": req.name or f"{agent['name']} on {ds['name']}", "dataset_id": ds["_id"],
               "dataset_name": ds["name"], "agent_id": agent["_id"], "agent_name": agent["name"],
               "agent_version": version, "source": req.source, "scorer": req.scorer.model_dump(), "items": items,
               "status": "running", "results": [], "summary": None, "created_by": user_id, "created_at": t,
               "finished_at": None}
        await self.evals.col.insert_one(doc)
        await self.audit.record(ws_id, user_id, "evaluation.create", "eval_run", eval_id,
                                {"dataset_id": ds["_id"], "agent_id": agent["_id"], "cases": len(items)})
        return await self.refresh(doc)

    async def refresh(self, ev: dict) -> dict:
        """Scores whatever finished. Freezes the evaluation once every case run is terminal."""
        if ev["status"] == "completed":
            return ev
        ids = [i["run_id"] for i in ev["items"]]
        q = {"workspace_id": ev["workspace_id"], "_id": {"$in": ids}}
        runs = {r["_id"]: r async for r in self.db["runs"].find(q)}
        results = []
        for item in ev["items"]:
            r = runs.get(item["run_id"])
            status = r["status"] if r else "failed"
            text = ((r or {}).get("output") or {}).get("text")
            passed, reason = None, "waiting for the worker"
            if status == "completed":
                passed, reason = score(ev["scorer"], text or "", item["expected"])
            elif status in TERMINAL or not r:
                err = (r or {}).get("error") or {}
                passed, reason = False, f"run {status}: {err.get('message', 'run missing')}"
            latency = None
            if r and r.get("started_at") and r.get("finished_at"):
                latency = int((r["finished_at"] - r["started_at"]).total_seconds() * 1000)
            cost = float(((r or {}).get("usage") or {}).get("cost_usd", 0.0))
            results.append({**item, "status": status, "output": text, "passed": passed, "reason": reason,
                            "latency_ms": latency, "cost_usd": cost})
        fields = {"results": results, "summary": summarize(results)}
        if all(x["status"] in TERMINAL for x in results):
            fields |= {"status": "completed", "finished_at": now()}
        await self.evals.col.update_one({"_id": ev["_id"], "status": "running"}, {"$set": fields})
        return {**ev, **fields}

    async def get_run(self, ws_id: str, eval_id: str) -> dict:
        ev = await self.evals.get(ws_id, eval_id)
        if not ev:
            raise NotFound("Evaluation run not found")
        return await self.refresh(ev)

    async def list_runs(self, ws_id: str, dataset_id: str | None, limit: int) -> list[dict]:
        f = {"dataset_id": dataset_id} if dataset_id else {}
        items, _ = await self.evals.list(ws_id, f, limit=limit)
        return [await self.refresh(e) for e in items]

    async def delete_run(self, ws_id: str, user_id: str, eval_id: str) -> None:
        r = await self.evals.col.delete_one({"_id": eval_id, "workspace_id": ws_id})
        if r.deleted_count == 0:
            raise NotFound("Evaluation run not found")
        await self.audit.record(ws_id, user_id, "evaluation.delete", "eval_run", eval_id)

    async def compare(self, ws_id: str, a_id: str, b_id: str) -> dict:
        a, b = await self.get_run(ws_id, a_id), await self.get_run(ws_id, b_id)
        if a["dataset_id"] != b["dataset_id"]:
            raise Unprocessable("Both evaluation runs must use the same dataset", code="DATASET_MISMATCH")
        ra = {x["case_id"]: x for x in a["results"]}
        rb = {x["case_id"]: x for x in b["results"]}
        rows, fixed, regressed = [], 0, 0
        for cid in list(dict.fromkeys([*ra, *rb])):
            x, y = ra.get(cid), rb.get(cid)
            base = x or y
            if not x or not y:
                change = "missing"
            elif not x["passed"] and y["passed"]:
                change, fixed = "fixed", fixed + 1
            elif x["passed"] and not y["passed"]:
                change, regressed = "regressed", regressed + 1
            else:
                change = "same_pass" if y["passed"] else "same_fail"
            rows.append({"case_id": cid, "input": base["input"], "expected": base["expected"], "a": x, "b": y,
                         "change": change})
        return {"a": present_eval(a), "b": present_eval(b), "rows": rows, "fixed": fixed, "regressed": regressed}


def summarize(results: list[dict]) -> dict:
    finished = [r for r in results if r["passed"] is not None]
    passed = sum(1 for r in finished if r["passed"])
    errors = sum(1 for r in finished if r["status"] != "completed")
    lat = [r["latency_ms"] for r in finished if r["latency_ms"] is not None]
    return {"total": len(results), "finished": len(finished), "passed": passed, "failed": len(finished) - passed,
            "errors": errors, "pass_rate": round(passed / len(finished), 4) if finished else None,
            "avg_latency_ms": int(sum(lat) / len(lat)) if lat else None,
            "cost_usd": round(sum(r["cost_usd"] for r in results), 8)}


def present_eval(e: dict) -> dict:
    return {**e, "id": e["_id"], "summary": e.get("summary") or summarize(e.get("results") or [])}

