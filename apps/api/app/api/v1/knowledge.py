from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.deps import Ctx, db_dep, require
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.schemas.common import Page
from app.schemas.knowledge import (
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    SearchHit,
    SearchRequest,
    TextDocumentCreate,
)
from app.services.knowledge import KnowledgeService, present_doc, present_kb

router = APIRouter(tags=["knowledge"])


class PayloadTooLarge(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
async def list_kbs(ctx: Ctx = Depends(require("knowledge:read")), db=Depends(db_dep)):
    return [present_kb(k) for k in await KnowledgeService(db).list_kbs(ctx.workspace_id)]


@router.post("/knowledge-bases", response_model=KnowledgeBaseOut, status_code=201)
async def create_kb(body: KnowledgeBaseCreate, ctx: Ctx = Depends(require("knowledge:write")), db=Depends(db_dep)):
    emb = body.embedding.model_dump() if body.embedding else None
    return present_kb(await KnowledgeService(db).create_kb(ctx.workspace_id, ctx.user_id, body.name,
                                                           body.description, emb))


@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseOut)
async def get_kb(kb_id: str, ctx: Ctx = Depends(require("knowledge:read")), db=Depends(db_dep)):
    return present_kb(await KnowledgeService(db).get_kb(ctx.workspace_id, kb_id))


@router.patch("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseOut)
async def update_kb(kb_id: str, body: KnowledgeBaseUpdate, ctx: Ctx = Depends(require("knowledge:write")),
                    db=Depends(db_dep)):
    return present_kb(await KnowledgeService(db).update_kb(ctx.workspace_id, ctx.user_id, kb_id,
                                                           body.model_dump(exclude_unset=True)))


@router.delete("/knowledge-bases/{kb_id}", status_code=204)
async def delete_kb(kb_id: str, ctx: Ctx = Depends(require("knowledge:write")), db=Depends(db_dep)):
    await KnowledgeService(db).delete_kb(ctx.workspace_id, ctx.user_id, kb_id)


@router.post("/knowledge-bases/{kb_id}/documents/upload", response_model=DocumentOut, status_code=202)
async def upload_document(kb_id: str, file: UploadFile = File(...), title: str | None = Form(None, max_length=300),
                          ctx: Ctx = Depends(require("knowledge:write")), db=Depends(db_dep)):
    """Stores the file and queues it for ingestion by the worker (extract, chunk, embed)."""
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"File exceeds {limit} bytes")
    name = file.filename or "document.txt"
    return present_doc(await KnowledgeService(db).add_document(ctx.workspace_id, ctx.user_id, kb_id,
                                                               title or name, name, data, "upload"))


@router.post("/knowledge-bases/{kb_id}/documents/text", response_model=DocumentOut, status_code=202)
async def add_text_document(kb_id: str, body: TextDocumentCreate, ctx: Ctx = Depends(require("knowledge:write")),
                            db=Depends(db_dep)):
    return present_doc(await KnowledgeService(db).add_document(ctx.workspace_id, ctx.user_id, kb_id, body.title,
                                                               "text.md", body.text.encode(), "text"))


@router.get("/documents", response_model=Page[DocumentOut])
async def list_documents(ctx: Ctx = Depends(require("knowledge:read")), db=Depends(db_dep),
                         kb_id: str | None = Query(None, max_length=64),
                         limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    items, total = await KnowledgeService(db).list_docs(ctx.workspace_id, kb_id, limit, offset)
    return {"items": [present_doc(d) for d in items], "total": total, "limit": limit, "offset": offset}


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, ctx: Ctx = Depends(require("knowledge:write")), db=Depends(db_dep)):
    await KnowledgeService(db).delete_doc(ctx.workspace_id, ctx.user_id, doc_id)


@router.post("/documents/{doc_id}/reindex", response_model=DocumentOut, status_code=202)
async def reindex_document(doc_id: str, ctx: Ctx = Depends(require("knowledge:write")), db=Depends(db_dep)):
    return present_doc(await KnowledgeService(db).reindex_doc(ctx.workspace_id, ctx.user_id, doc_id))


@router.post("/knowledge-bases/{kb_id}/search", response_model=list[SearchHit])
async def search(kb_id: str, body: SearchRequest, ctx: Ctx = Depends(require("knowledge:read")), db=Depends(db_dep)):
    svc = KnowledgeService(db)
    await svc.get_kb(ctx.workspace_id, kb_id)
    return await svc.search(ctx.workspace_id, [kb_id], body.query, body.top_k)
