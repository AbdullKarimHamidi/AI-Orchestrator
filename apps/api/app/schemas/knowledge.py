from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, OutModel


class EmbeddingRef(ApiModel):
    provider_id: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=200)


class KnowledgeBaseCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    embedding: EmbeddingRef | None = Field(default=None, description="None = built-in lexical search")


class KnowledgeBaseUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    embedding: EmbeddingRef | None = None


class KnowledgeBaseOut(OutModel):
    id: str
    name: str
    description: str
    embedding: dict | None
    doc_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class TextDocumentCreate(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=900_000)


class DocumentOut(OutModel):
    id: str
    kb_id: str
    title: str
    filename: str | None
    source: Literal["upload", "text"]
    bytes: int
    status: Literal["queued", "processing", "ready", "failed"]
    error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class SearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchHit(OutModel):
    kb_id: str
    doc_id: str
    title: str
    chunk: int
    text: str
    score: float
