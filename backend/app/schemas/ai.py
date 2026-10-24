"""AI katmanı ile ilgili Pydantic modelleri."""

from typing import Literal
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


class HybridSearchRequest(BaseModel):
    """Hybrid (vektör + BM25 + RRF) arama isteği."""

    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="0=BM25, 1=vektör")
    # True ise hybrid adaylar cross-encoder rerank'ten geçer (varsayılan).
    use_rerank: bool = True
    rerank_candidates: int = Field(default=20, ge=1, le=50, description="Rerank öncesi aday sayısı")
    # Parent retrieval: en iyi chunk'ın başlığındaki diğer chunk'lar da döner.
    expand_context: bool = False


class SearchResultItem(BaseModel):
    """Tek bir chunk arama sonucu."""

    chunk_id: UUID
    document_id: UUID
    content: str
    similarity: float
    chunk_index: int
    # Hybrid aramada dolu: chunk'ın hangi kaynaktan geldiği; /search'te None.
    retrieval_source: Literal["vector", "bm25", "both"] | None = None
    # Cross-encoder rerank skoru; yalnızca use_rerank=True iken dolu.
    rerank_score: float | None = None
    # Hiyerarşik chunking: chunk'ın başlık zinciri ("Ana > Alt"); eski chunk'larda None.
    heading: str | None = None
    # Parent retrieval ile eklenen bağlam chunk'ı işareti (skorlanmamış).
    expanded: bool | None = None


class SearchResponse(BaseModel):
    """RAG arama yanıtı."""

    query: str
    results: list[SearchResultItem]


class ChatRequest(BaseModel):
    """Chat (SSE streaming) isteği."""

    query: str = Field(min_length=1, max_length=2000)
    document_ids: list[UUID] | None = None
    top_k: int = Field(default=5, ge=1, le=10)
    # True (varsayılan) ise cevaptan sonra citation doğrulaması + hallucination
    # tespiti çalışır ve "verification" SSE event'i gönderilir.
    verify: bool = True


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


class CorrectiveChatRequest(BaseModel):
    """Self-critique / corrective RAG isteği."""

    query: str = Field(min_length=1, max_length=2000)
    max_retries: int = Field(default=2, ge=0, le=3, description="Critique-revision tur sayısı")


class TestSetItem(BaseModel):
    """Sentetik test seti elemanı: soru + doğru cevap."""

    question: str = Field(min_length=1, max_length=2000)
    ground_truth: str = Field(default="", max_length=8000)


class GenerateTestSetRequest(BaseModel):
    """Sentetik test seti üretme isteği."""

    document_id: UUID
    num_questions: int = Field(default=5, ge=1, le=10)


class GenerateTestSetResponse(BaseModel):
    """Sentetik test seti yanıtı."""

    document_id: UUID
    questions: list[TestSetItem]


class EvaluationRunRequest(BaseModel):
    """RAGAS değerlendirme isteği."""

    test_set: list[TestSetItem] = Field(min_length=1)


class EvaluationMetrics(BaseModel):
    """RAGAS metrikleri (müşteri hedefleri: F≥0.85, CP≥0.75, AR≥0.80)."""

    faithfulness: float
    answer_relevancy: float
    context_precision: float


class EvaluationRunResponse(BaseModel):
    """RAGAS değerlendirme yanıtı."""

    metrics: EvaluationMetrics
    samples: int


class FeedbackRequest(BaseModel):
    """Kullanıcı geri bildirimi (1 = thumbs up, 0 = thumbs down)."""

    trace_id: str = Field(min_length=1, max_length=128)
    score: int = Field(ge=0, le=1)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    """Geri bildirim yanıtı."""

    status: str
