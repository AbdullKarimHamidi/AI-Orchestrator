from datetime import datetime, timedelta

from pymongo import ReturnDocument

from app.repositories.base import ScopedRepository, now


class KnowledgeBaseRepository(ScopedRepository):
    collection_name = "knowledge_bases"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def get(self, workspace_id: str, _id: str) -> dict | None:
        return await self.col.find_one({"_id": _id, "workspace_id": workspace_id, "deleted": False})

    async def many(self, workspace_id: str, ids: list[str]) -> list[dict]:
        return [d async for d in self.col.find({"workspace_id": workspace_id, "_id": {"$in": ids}, "deleted": False})]

    async def update(self, workspace_id: str, _id: str, fields: dict, inc: dict | None = None) -> dict | None:
        upd: dict = {"$set": {**fields, "updated_at": now()}}
        if inc:
            upd["$inc"] = inc
        return await self.col.find_one_and_update({"_id": _id, "workspace_id": workspace_id}, upd,
                                                  return_document=ReturnDocument.AFTER)


class DocumentRepository(ScopedRepository):
    collection_name = "documents"

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(doc)

    async def update(self, workspace_id: str, _id: str, fields: dict) -> dict | None:
        return await self.col.find_one_and_update({"_id": _id, "workspace_id": workspace_id},
                                                  {"$set": {**fields, "updated_at": now()}},
                                                  return_document=ReturnDocument.AFTER)

    # ----- worker-side ingestion queue (same lease pattern as runs) -----
    async def claim(self, worker_id: str, lease_seconds: int) -> dict | None:
        t = now()
        return await self.col.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "processing", "lease_owner": worker_id,
                      "lease_expires_at": t + timedelta(seconds=lease_seconds), "updated_at": t},
             "$inc": {"attempts": 1}},
            sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)

    async def finish(self, _id: str, worker_id: str, fields: dict) -> bool:
        r = await self.col.update_one({"_id": _id, "lease_owner": worker_id, "status": "processing"},
                                      {"$set": {**fields, "lease_owner": None, "lease_expires_at": None,
                                                "updated_at": now()}})
        return r.modified_count == 1

    async def recover_expired(self, t: datetime, max_attempts: int = 3) -> int:
        n = 0
        async for d in self.col.find({"status": "processing", "lease_expires_at": {"$lt": t}}).limit(50):
            status = "queued" if d.get("attempts", 0) < max_attempts else "failed"
            fields: dict = {"status": status, "lease_owner": None, "lease_expires_at": None, "updated_at": t}
            if status == "failed":
                fields["error"] = "ingestion worker was lost repeatedly"
            r = await self.col.update_one({"_id": d["_id"], "status": "processing",
                                           "lease_expires_at": d["lease_expires_at"]}, {"$set": fields})
            n += r.modified_count
        return n


class ChunkRepository:
    def __init__(self, db):
        self.col = db["chunks"]

    async def insert_many(self, docs: list[dict]) -> None:
        if docs:
            await self.col.insert_many(docs, ordered=False)

    async def delete_for_doc(self, workspace_id: str, doc_id: str) -> None:
        await self.col.delete_many({"workspace_id": workspace_id, "doc_id": doc_id})

    async def delete_for_kb(self, workspace_id: str, kb_id: str) -> None:
        await self.col.delete_many({"workspace_id": workspace_id, "kb_id": kb_id})
