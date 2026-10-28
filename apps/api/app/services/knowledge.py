"""Knowledge bases (retrieval-augmented generation).

Flow: upload (raw file -> GridFS, document 'queued') -> worker ingestion (extract text, chunk,
embed, store chunks, 'ready') -> retrieval at run time (cosine similarity over the knowledge
base's vectors, top-k chunks injected into the system prompt with numbered sources).

Vectors are float32 in the ``chunks`` collection. Search loads a knowledge base's matrix once and
caches it in-process until the knowledge base's ``version`` changes, which keeps search fast on
MongoDB Community (no Atlas Vector Search needed) for knowledge bases up to ~100k chunks.
"""
import asyncio
import logging
from collections import OrderedDict

import numpy as np
from bson import Binary
from gridfs import AsyncGridFSBucket
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.core.exceptions import Conflict, NotFound, Unprocessable
from app.core.ids import new_id
from app.knowledge.embeddings import embed_texts
from app.knowledge.parsing import SUPPORTED, chunk_text, extract_text
from app.providers.base import ProviderError
from app.repositories.audit import AuditRepository
from app.repositories.base import now
from app.repositories.knowledge import ChunkRepository, DocumentRepository, KnowledgeBaseRepository
from app.repositories.providers import ProviderRepository
from app.services.providers import runtime_config

log = logging.getLogger(__name__)

EMBED_KINDS = {"openai", "openai_compatible", "gemini"}


def present_kb(k: dict) -> dict:
    return {"id": k["_id"], "name": k["name"], "description": k.get("description", ""),
            "embedding": k.get("embedding"), "doc_count": k.get("doc_count", 0),
            "chunk_count": k.get("chunk_count", 0), "created_at": k["created_at"],
            "updated_at": k.get("updated_at", k["created_at"])}


def present_doc(d: dict) -> dict:
    return {"id": d["_id"], "kb_id": d["kb_id"], "title": d["title"], "filename": d.get("filename"),
            "source": d.get("source", "upload"), "bytes": d.get("bytes", 0), "status": d["status"],
            "error": d.get("error"), "chunk_count": d.get("chunk_count", 0), "created_at": d["created_at"],
            "updated_at": d.get("updated_at", d["created_at"])}


def _bucket(db: AsyncDatabase) -> AsyncGridFSBucket:
    return AsyncGridFSBucket(db, bucket_name="document_blobs")


class _MatrixCache:
    """kb_id -> (version, ids, matrix). Small LRU; both API and worker processes keep one."""

    def __init__(self, size: int = 32):
        self.size = size
        self.items: OrderedDict[str, tuple[int, list, np.ndarray]] = OrderedDict()

    def get(self, kb_id: str, version: int):
        hit = self.items.get(kb_id)
        if hit and hit[0] == version:
            self.items.move_to_end(kb_id)
            return hit
        return None

    def put(self, kb_id: str, value: tuple[int, list, np.ndarray]) -> None:
        self.items[kb_id] = value
        self.items.move_to_end(kb_id)
        while len(self.items) > self.size:
            self.items.popitem(last=False)


_cache = _MatrixCache()


class KnowledgeService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.kbs = KnowledgeBaseRepository(db)
        self.docs = DocumentRepository(db)
        self.chunks = ChunkRepository(db)
        self.providers = ProviderRepository(db)
        self.audit = AuditRepository(db)

    # ----- knowledge bases -----
    async def get_kb(self, ws_id: str, kb_id: str) -> dict:
        k = await self.kbs.get(ws_id, kb_id)
        if not k:
            raise NotFound("Knowledge base not found")
        return k

    async def list_kbs(self, ws_id: str) -> list[dict]:
        items, _ = await self.kbs.list(ws_id, {"deleted": False}, sort=[("name_lower", 1)], limit=500)
        return items

    async def _check_embedding(self, ws_id: str, emb: dict | None) -> None:
        if not emb:
            return
        p = await self.providers.get(ws_id, emb["provider_id"])
        if not p:
            raise Unprocessable("Embedding provider not found", code="PROVIDER_NOT_FOUND")
        if p["kind"] not in EMBED_KINDS:
            raise Unprocessable(f"{p['kind']} providers have no embeddings API; use OpenAI, Gemini, an "
                                "OpenAI-compatible server, or the built-in lexical search", code="NO_EMBEDDINGS")

    async def create_kb(self, ws_id: str, user_id: str, name: str, description: str, emb: dict | None) -> dict:
        await self._check_embedding(ws_id, emb)
        t = now()
        doc = {"_id": new_id("kb"), "workspace_id": ws_id, "name": name, "name_lower": name.lower(),
               "description": description, "embedding": emb, "doc_count": 0, "chunk_count": 0, "version": 0,
               "created_by": user_id, "created_at": t, "updated_at": t, "deleted": False}
        try:
            await self.kbs.insert(doc)
        except DuplicateKeyError as exc:
            raise Conflict("A knowledge base with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "knowledge.create", "knowledge_base", doc["_id"])
        return doc

    async def update_kb(self, ws_id: str, user_id: str, kb_id: str, fields: dict) -> dict:
        k = await self.get_kb(ws_id, kb_id)
        upd: dict = {}
        if "name" in fields:
            upd |= {"name": fields["name"], "name_lower": fields["name"].lower()}
        if "description" in fields:
            upd["description"] = fields["description"]
        if "embedding" in fields and fields["embedding"] != k.get("embedding"):
            if k.get("doc_count"):
                raise Conflict("The embedding model cannot change once documents exist (vectors would not match). "
                               "Create a new knowledge base instead.", code="EMBEDDING_LOCKED")
            await self._check_embedding(ws_id, fields["embedding"])
            upd["embedding"] = fields["embedding"]
        try:
            updated = await self.kbs.update(ws_id, kb_id, upd)
        except DuplicateKeyError as exc:
            raise Conflict("A knowledge base with this name already exists", code="NAME_TAKEN") from exc
        await self.audit.record(ws_id, user_id, "knowledge.update", "knowledge_base", kb_id, {"fields": sorted(upd)})
        return updated  # type: ignore[return-value]

    async def delete_kb(self, ws_id: str, user_id: str, kb_id: str) -> None:
        await self.get_kb(ws_id, kb_id)
        await self.kbs.update(ws_id, kb_id, {"deleted": True, "name_lower": f"{kb_id}:deleted"})
        await self.chunks.delete_for_kb(ws_id, kb_id)
        async for d in self.docs.col.find({"workspace_id": ws_id, "kb_id": kb_id}, {"blob_id": 1}):
            await self._drop_blob(d.get("blob_id"))
        await self.docs.col.delete_many({"workspace_id": ws_id, "kb_id": kb_id})
        await self.audit.record(ws_id, user_id, "knowledge.delete", "knowledge_base", kb_id)

    # ----- documents -----
    async def add_document(self, ws_id: str, user_id: str, kb_id: str, title: str, filename: str,
                           data: bytes, source: str) -> dict:
        await self.get_kb(ws_id, kb_id)
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if ext and ext not in SUPPORTED:
            raise Unprocessable(f"Unsupported file type {ext}. Supported: {', '.join(SUPPORTED)}",
                                code="UNSUPPORTED_DOCUMENT")
        if not data:
            raise Unprocessable("The document is empty", code="EMPTY_DOCUMENT")
        blob_id = await _bucket(self.db).upload_from_stream(filename or "document.txt", data,
                                                            metadata={"workspace_id": ws_id})
        t = now()
        doc = {"_id": new_id("doc"), "workspace_id": ws_id, "kb_id": kb_id, "title": title[:300],
               "filename": filename, "source": source, "bytes": len(data), "status": "queued", "error": None,
               "chunk_count": 0, "blob_id": blob_id, "attempts": 0, "lease_owner": None, "lease_expires_at": None,
               "created_by": user_id, "created_at": t, "updated_at": t}
        await self.docs.insert(doc)
        await self.kbs.update(ws_id, kb_id, {}, inc={"doc_count": 1})
        await self.audit.record(ws_id, user_id, "knowledge.document_add", "document", doc["_id"],
                                {"kb_id": kb_id, "bytes": len(data)})
        return doc

    async def list_docs(self, ws_id: str, kb_id: str | None, limit: int, offset: int):
        f = {"kb_id": kb_id} if kb_id else {}
        return await self.docs.list(ws_id, f, limit=limit, offset=offset)

    async def delete_doc(self, ws_id: str, user_id: str, doc_id: str) -> None:
        d = await self.docs.get(ws_id, doc_id)
        if not d:
            raise NotFound("Document not found")
        await self.chunks.delete_for_doc(ws_id, doc_id)
        await self.docs.col.delete_one({"_id": doc_id, "workspace_id": ws_id})
        await self._drop_blob(d.get("blob_id"))
        await self.kbs.update(ws_id, d["kb_id"], {}, inc={"doc_count": -1, "chunk_count": -d.get("chunk_count", 0),
                                                          "version": 1})
        await self.audit.record(ws_id, user_id, "knowledge.document_delete", "document", doc_id)

    async def reindex_doc(self, ws_id: str, user_id: str, doc_id: str) -> dict:
        d = await self.docs.get(ws_id, doc_id)
        if not d:
            raise NotFound("Document not found")
        if not d.get("blob_id"):
            raise Conflict("The original file is no longer stored; upload it again", code="BLOB_MISSING")
        updated = await self.docs.update(ws_id, doc_id, {"status": "queued", "error": None, "attempts": 0})
        await self.audit.record(ws_id, user_id, "knowledge.document_reindex", "document", doc_id)
        return updated  # type: ignore[return-value]

    async def _drop_blob(self, blob_id) -> None:
        if blob_id is None:
            return
        try:
            await _bucket(self.db).delete(blob_id)
        except Exception:  # noqa: BLE001 - already gone is fine
            log.debug("blob %s already deleted", blob_id)

    # ----- ingestion (worker) -----
    async def _embedding_config(self, ws_id: str, kb: dict):
        emb = kb.get("embedding")
        if not emb:
            return None, None
        p = await self.providers.get(ws_id, emb["provider_id"])
        if not p:
            raise ProviderError("not_found", "embedding provider was deleted")
        return runtime_config(p), emb["model"]

    async def ingest(self, d: dict) -> dict:
        """Returns the fields to store on the document (status ready/failed)."""
        ws = d["workspace_id"]
        kb = await self.kbs.get(ws, d["kb_id"])
        if not kb:
            return {"status": "failed", "error": "knowledge base was deleted"}
        s = get_settings()
        try:
            stream = await _bucket(self.db).open_download_stream(d["blob_id"])
            data = await stream.read()
            text = await asyncio.to_thread(extract_text, d.get("filename") or "document.txt", data)
            pieces = chunk_text(text, s.knowledge_chunk_chars, s.knowledge_chunk_overlap)
            cfg, model = await self._embedding_config(ws, kb)
            vectors = await embed_texts(cfg, model, pieces)
        except ProviderError as exc:
            return {"status": "failed", "error": f"embedding failed: {exc.kind}: {exc.message}"[:1000]}
        except ValueError as exc:
            return {"status": "failed", "error": str(exc)[:1000]}
        await self.chunks.delete_for_doc(ws, d["_id"])
        await self.chunks.insert_many([
            {"_id": new_id("chk"), "workspace_id": ws, "kb_id": kb["_id"], "doc_id": d["_id"], "idx": i,
             "title": d["title"], "text": t, "vector": Binary(np.asarray(v, dtype=np.float32).tobytes())}
            for i, (t, v) in enumerate(zip(pieces, vectors, strict=True))])
        await self.kbs.update(ws, kb["_id"], {}, inc={"chunk_count": len(pieces) - d.get("chunk_count", 0),
                                                      "version": 1})
        return {"status": "ready", "error": None, "chunk_count": len(pieces), "chars": len(text)}

    # ----- retrieval -----
    async def _matrix(self, kb: dict) -> tuple[list, np.ndarray]:
        version = kb.get("version", 0)
        hit = _cache.get(kb["_id"], version)
        if hit:
            return hit[1], hit[2]
        ids, vecs = [], []
        async for c in self.chunks.col.find({"workspace_id": kb["workspace_id"], "kb_id": kb["_id"]},
                                            {"_id": 1, "vector": 1}):
            ids.append(c["_id"])
            vecs.append(np.frombuffer(c["vector"], dtype=np.float32))
        dims = {v.shape[0] for v in vecs}
        matrix = np.vstack(vecs) if vecs and len(dims) == 1 else np.zeros((0, 1), dtype=np.float32)
        _cache.put(kb["_id"], (version, ids, matrix))
        return ids, matrix

    async def search(self, ws_id: str, kb_ids: list[str], query: str, top_k: int = 5,
                     min_score: float = 0.0) -> list[dict]:
        scored: list[tuple[float, str]] = []
        for kb in await self.kbs.many(ws_id, kb_ids):
            ids, matrix = await self._matrix(kb)
            if not ids:
                continue
            cfg, model = await self._embedding_config(ws_id, kb)
            q = np.asarray((await embed_texts(cfg, model, [query]))[0], dtype=np.float32)
            if q.shape[0] != matrix.shape[1]:
                continue
            scores = matrix @ q
            k = min(top_k, len(ids))
            for i in np.argpartition(-scores, k - 1)[:k]:
                if scores[i] > min_score:
                    scored.append((float(scores[i]), ids[i]))
        scored.sort(reverse=True)
        best = scored[:top_k]
        docs = {c["_id"]: c async for c in self.chunks.col.find({"_id": {"$in": [i for _, i in best]}},
                                                                 {"vector": 0})}
        return [{"kb_id": docs[i]["kb_id"], "doc_id": docs[i]["doc_id"], "title": docs[i]["title"],
                 "chunk": docs[i]["idx"], "text": docs[i]["text"], "score": round(s, 4)}
                for s, i in best if i in docs]
