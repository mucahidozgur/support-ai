"""AI katmanı ile ilgili Pydantic modelleri."""

from uuid import UUID

from pydantic import BaseModel, Field


class IndexResponse(BaseModel):
    """Index'leme sonucu."""

    document_id: UUID
    chunks_created: int
    chunks_deleted: int


class SearchRequest(BaseModel):
    """RAG arama isteği."""

    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[UUID] | None = None
    limit: int = Field(default=5, ge=1, le=20)


class SearchResultItem(BaseModel):
    """Tek bir chunk arama sonucu."""

    chunk_id: UUID
    document_id: UUID
    content: str
    similarity: float
    chunk_index: int


class SearchResponse(BaseModel):
    """RAG arama yanıtı."""

    query: str
    results: list[SearchResultItem]


class ChatRequest(BaseModel):
    """Chat (SSE streaming) isteği."""

    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[UUID] | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class ChatSource(BaseModel):
    """SSE "sources" event'i için kaynak bilgisi."""

    document_id: UUID
    document_title: str
    chunk_id: UUID
    chunk_index: int
    similarity: float


class ChatTokenEvent(BaseModel):
    """SSE "token" event'i."""

    text: str


class ChatDoneEvent(BaseModel):
    """SSE "done" event'i."""

    finish_reason: str
    tokens_used: int | None = None


class ChatErrorEvent(BaseModel):
    """SSE "error" event'i."""

    message: str
