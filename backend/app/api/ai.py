"""AI endpoint'leri: RAG arama ve SSE streaming chat."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.observability import get_langfuse_client
from app.schemas.ai import (
    ChatRequest,
    EvaluationMetrics,
    EvaluationRunRequest,
    EvaluationRunResponse,
    FeedbackRequest,
    FeedbackResponse,
    GenerateTestSetRequest,
    GenerateTestSetResponse,
    HybridSearchRequest,
    SearchRequest,
    SearchResponse,
)
from app.schemas.auth import UserInfo
from app.services.agent import AgentService
from app.services.chat import ChatService
from app.services.evaluation import EvaluationError, evaluate_rag, generate_test_set
from app.services.rag import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[UserInfo, Depends(get_current_user)]


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest, db: DbDep, current_user: UserDep) -> SearchResponse:
    """RAG ile en alakalı chunk'ları arar."""
    results = await RAGService(db, UUID(current_user.id)).search(
        body.query, body.document_ids, body.limit
    )
    return SearchResponse(query=body.query, results=results)


@router.post("/search/hybrid", response_model=SearchResponse)
async def search_hybrid(
    body: HybridSearchRequest, db: DbDep, current_user: UserDep
) -> SearchResponse:
    """Vektör + BM25 aramalarını RRF ile birleştirip en alakalı chunk'ları döndürür.

    use_rerank=True ise (varsayılan) adaylar cross-encoder rerank'ten geçirilir;
    expand_context=True ise en iyi chunk'ın başlığındaki diğer chunk'lar da eklenir.
    """
    if body.expand_context and not body.use_rerank:
        raise HTTPException(
            status_code=400, detail="expand_context yalnızca use_rerank=True ile kullanılabilir"
        )
    service = RAGService(db, UUID(current_user.id))
    if body.use_rerank:
        results = await service.search_hybrid_rerank(
            body.query,
            body.limit,
            body.alpha,
            body.rerank_candidates,
            expand_context=body.expand_context,
        )
    else:
        results = await service.search_hybrid(body.query, body.limit, body.alpha)
    return SearchResponse(query=body.query, results=results)


@router.post("/chat")
async def chat(body: ChatRequest, db: DbDep, current_user: UserDep) -> EventSourceResponse:
    """RAG context'i ile SSE streaming chat yanıtı döndürür."""
    owner_id = UUID(current_user.id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            service = ChatService(db, owner_id)
            async for event in service.stream_chat(
                body.query, body.document_ids, body.top_k, verify=body.verify
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], default=str),
                }
        except Exception as exc:
            logger.exception("Chat stream error")
            yield {
                "event": "error",
                "data": json.dumps({"message": str(exc)}),
            }
            yield {
                "event": "done",
                "data": json.dumps({"finish_reason": "error"}),
            }
        finally:
            # FastAPI, StreamingResponse'da yield-bağımlılıklarını stream başlamadan
            # kapatır; generator içinde yeniden checkout edilen bağlantıyı burada
            # iade et (aksi halde her stream isteği pool'dan bağlantı sızdırır).
            await db.close()

    # ping saniye cinsindendir: 15 sn'de bir keepalive (bazı proxy'ler için gerekli)
    return EventSourceResponse(event_generator(), ping=15)


@router.post("/agent")
async def agent(body: ChatRequest, db: DbDep, current_user: UserDep) -> EventSourceResponse:
    """LangGraph agent: router ile niyet tespiti + SSE streaming yanıt."""
    owner_id = UUID(current_user.id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            service = AgentService(db, owner_id)
            async for event in service.stream_agent(body.query, body.document_ids, body.top_k):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], default=str),
                }
        except Exception as exc:
            logger.exception("Agent stream error")
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}
            yield {"event": "done", "data": json.dumps({"finish_reason": "error"})}
        finally:
            # /chat ile aynı neden: stream sonunda bağlantıyı pool'a iade et.
            await db.close()

    return EventSourceResponse(event_generator(), ping=15)


@router.post("/evaluate/generate-set", response_model=GenerateTestSetResponse)
async def evaluate_generate_set(
    body: GenerateTestSetRequest, db: DbDep, current_user: UserDep
) -> GenerateTestSetResponse:
    """Dokümandan LLM ile sentetik soru-cevap (test seti) üretir."""
    try:
        questions = await generate_test_set(
            db, UUID(current_user.id), body.document_id, body.num_questions
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EvaluationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if questions is None:
        raise HTTPException(status_code=404, detail="Doküman bulunamadı")
    return GenerateTestSetResponse(document_id=body.document_id, questions=questions)


@router.post("/evaluate/run", response_model=EvaluationRunResponse)
async def evaluate_run(
    body: EvaluationRunRequest, db: DbDep, current_user: UserDep
) -> EvaluationRunResponse:
    """Test setini RAGAS metrikleriyle değerlendirir."""
    test_set = [item.model_dump() for item in body.test_set]
    try:
        metrics = await evaluate_rag(test_set, RAGService(db, UUID(current_user.id)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EvaluationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return EvaluationRunResponse(metrics=EvaluationMetrics(**metrics), samples=len(test_set))


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(body: FeedbackRequest, current_user: UserDep) -> FeedbackResponse:
    """Langfuse'a kullanıcı geri bildirimi (thumbs up/down) gönderir.

    Observability devre dışıysa 503; Langfuse hatasında 502 döner — akışı bozmaz.
    """
    client = get_langfuse_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Observability devre dışı")
    try:
        client.create_score(
            name="user_feedback",
            value=float(body.score),
            trace_id=body.trace_id,
            comment=body.comment,
        )
    except Exception as exc:
        logger.warning("Langfuse feedback gönderilemedi: %s", exc)
        raise HTTPException(status_code=502, detail="Geri bildirim gönderilemedi") from exc
    return FeedbackResponse(status="ok")
