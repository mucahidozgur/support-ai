"""Chat servisi: RAG context'i ile SSE streaming yanıt üretir.

Akış: hybrid+rerank arama → güven eşiği kontrolü → LLM stream →
citation doğrulaması + hallucination tespiti (verification event'i).
Her istek query_logs'a yazılır (analitik panosu).
"""

import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.core.observability import callback_config
from app.models.query_log import QueryLog
from app.schemas.ai import ChatSource
from app.services.critique import critique_answer, rewrite_query
from app.services.prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt
from app.services.rag import RAGService, has_sufficient_context
from app.services.verification import detect_hallucination, verify_citations

logger = logging.getLogger(__name__)

INSUFFICIENT_CONTEXT_ANSWER = (
    "Bu bilgi knowledge base'de bulunmuyor. Lütfen ilgili dokümanı kontrol edin "
    "veya uzmanınıza danışın."
)


async def _write_query_log(
    db: AsyncSession,
    *,
    log_id: UUID,
    query: str,
    faithfulness: float | None,
    had_context: bool,
    latency_ms: int,
) -> None:
    """Sorgu metriğini query_logs'a yazar; hata stream'i asla bozmaz."""
    try:
        db.add(
            QueryLog(
                id=log_id,
                query=query[:2000],
                faithfulness=faithfulness,
                had_context=had_context,
                latency_ms=latency_ms,
            )
        )
        await db.commit()
    except Exception:
        logger.warning("Query log yazılamadı", exc_info=True)


class ChatService:
    """RAG destekli chat: arama → eşik → prompt → LLM stream → doğrulama."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.rag = RAGService(db, owner_id)
        # LLM lazy kurulur: context yetersizse hiç inşa edilmez (API key'siz
        # ortamda bile "bilgi yok" cevabı hatasız dönmelidir).
        self._llm_instance = None

    def _llm(self):
        """LLM'i ilk kullanımda kurar (lazy)."""
        if self._llm_instance is None:
            self._llm_instance = get_llm()
        return self._llm_instance

    async def stream_chat(
        self,
        query: str,
        document_ids: list[UUID] | None = None,
        top_k: int = 5,
        verify: bool = True,
    ) -> AsyncIterator[dict[str, object]]:
        """SSE event dict'leri üretir: sources, token, verification, done, error.

        Yeterli context yoksa LLM çağrılmaz; sabit "bilgi yok" cevabı stream
        edilir ve done event'i insufficient_context=true taşır. Her akış sonunda
        query_logs'a metrik yazılır; done event'i log_id taşır (feedback için).
        """
        start = time.perf_counter()
        log_id = uuid4()
        had_context = False
        faithfulness: float | None = None

        def _latency_ms() -> int:
            return int((time.perf_counter() - start) * 1000)

        try:
            if document_ids is not None:
                # Doküman filtresi istenmişse klasik vektör araması kullan
                # (hybrid servisinde filtre yok; MIN_SIMILARITY zaten uygulanır).
                chunks = await self.rag.search(query, document_ids, limit=top_k)
            else:
                chunks = await self.rag.search_hybrid_rerank(query=query, limit=top_k)

            if not has_sufficient_context(chunks):
                yield {"event": "sources", "data": []}
                yield {"event": "token", "data": {"text": INSUFFICIENT_CONTEXT_ANSWER}}
                await _write_query_log(
                    self.db,
                    log_id=log_id,
                    query=query,
                    faithfulness=None,
                    had_context=False,
                    latency_ms=_latency_ms(),
                )
                yield {
                    "event": "done",
                    "data": {
                        "finish_reason": "insufficient_context",
                        "insufficient_context": True,
                        "log_id": str(log_id),
                    },
                }
                return

            had_context = True
            sources = [ChatSource.model_validate(chunk).model_dump(mode="json") for chunk in chunks]
            yield {"event": "sources", "data": sources}

            context_block = build_context_block(chunks)
            messages = [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(build_user_prompt(query, context_block)),
            ]
            answer_parts: list[str] = []
            async for chunk in self._llm().astream(messages, config=callback_config()):
                if chunk.content:
                    answer_parts.append(chunk.content)
                    yield {"event": "token", "data": {"text": chunk.content}}

            if verify:
                verification = await self._verification_event(query, chunks, "".join(answer_parts))
                faithfulness = verification["data"].get("faithfulness")
                yield verification
            await _write_query_log(
                self.db,
                log_id=log_id,
                query=query,
                faithfulness=faithfulness,
                had_context=True,
                latency_ms=_latency_ms(),
            )
            yield {"event": "done", "data": {"finish_reason": "stop", "log_id": str(log_id)}}
        except Exception as exc:
            logger.exception("Chat stream error")
            await _write_query_log(
                self.db,
                log_id=log_id,
                query=query,
                faithfulness=None,
                had_context=had_context,
                latency_ms=_latency_ms(),
            )
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {"finish_reason": "error", "log_id": str(log_id)}}

    async def _verification_event(
        self, query: str, chunks: list[dict], answer: str
    ) -> dict[str, object]:
        """Citation doğrulaması + hallucination tespiti event'ini üretir.

        Doğrulama kendisi hata verse bile stream bozulmasın diye kendi
        try/except'inde çalışır; hata durumunda verified=False işaretlenir.
        """
        try:
            citation = verify_citations(answer, chunks)
            hallucination = detect_hallucination(answer, chunks)
            return {
                "event": "verification",
                "data": {
                    "verified": citation["verified"],
                    "unsupported": citation["unsupported_sentences"],
                    "faithfulness": hallucination["faithfulness"],
                },
            }
        except Exception:
            logger.exception("Verification error (query=%s)", query[:100])
            return {
                "event": "verification",
                "data": {"verified": False, "unsupported": [], "faithfulness": 0.0},
            }


class CorrectiveChatService:
    """Self-critique / corrective RAG akışı.

    Akış: hybrid+rerank arama → yetersizse rewrite_query ile yeniden ara →
    taslak cevap → critique_answer ile eleştiri → gerekirse düzeltilmiş cevabı
    kullan (max_retries kadar tekrar) → final cevabı SSE ile stream et.
    """

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.rag = RAGService(db, owner_id)
        self._llm_instance = None  # ChatService ile aynı nedenle lazy

    def _llm(self):
        if self._llm_instance is None:
            self._llm_instance = get_llm()
        return self._llm_instance

    async def corrective_rag_stream(
        self, query: str, max_retries: int = 2
    ) -> AsyncIterator[dict[str, object]]:
        """SSE event'leri üretir: sources, rewrite?, critique?, revision?, token, done."""
        start = time.perf_counter()
        log_id = uuid4()

        def _latency_ms() -> int:
            return int((time.perf_counter() - start) * 1000)

        try:
            chunks = await self.rag.search_hybrid_rerank(query=query, limit=5)

            # 2) Context yetersizse sorguyu yeniden yaz ve tekrar ara.
            if not has_sufficient_context(chunks):
                new_query = rewrite_query(query, chunks)
                yield {
                    "event": "rewrite",
                    "data": {"original_query": query, "new_query": new_query},
                }
                chunks = await self.rag.search_hybrid_rerank(query=new_query, limit=5)
                if not has_sufficient_context(chunks):
                    yield {"event": "sources", "data": []}
                    yield {"event": "token", "data": {"text": INSUFFICIENT_CONTEXT_ANSWER}}
                    await _write_query_log(
                        self.db,
                        log_id=log_id,
                        query=query,
                        faithfulness=None,
                        had_context=False,
                        latency_ms=_latency_ms(),
                    )
                    yield {
                        "event": "done",
                        "data": {
                            "finish_reason": "insufficient_context",
                            "insufficient_context": True,
                            "log_id": str(log_id),
                        },
                    }
                    return

            sources = [ChatSource.model_validate(c).model_dump(mode="json") for c in chunks]
            yield {"event": "sources", "data": sources}

            # 3) Taslak cevap (critique tam metni görmeli; invoke ile üretilir).
            context_block = build_context_block(chunks)
            draft = self._generate_draft(query, context_block)

            # 4) Self-critique: gerekirse düzeltilmiş cevabı kullan.
            answer = draft
            rounds = max_retries + 1
            for _ in range(rounds):
                result = critique_answer(query, answer, context_block)
                yield {
                    "event": "critique",
                    "data": {
                        "is_satisfactory": result["is_satisfactory"],
                        "critique": result["critique"],
                    },
                }
                if result["is_satisfactory"] or result["revised_answer"] == answer:
                    break
                answer = result["revised_answer"]
                yield {
                    "event": "revision",
                    "data": {"revised_answer": answer},
                }

            # 6) Final cevabı token olarak stream et (SSE formatı uyumlu).
            yield {"event": "token", "data": {"text": answer}}
            await _write_query_log(
                self.db,
                log_id=log_id,
                query=query,
                faithfulness=None,  # corrective akışta verification yok
                had_context=True,
                latency_ms=_latency_ms(),
            )
            yield {"event": "done", "data": {"finish_reason": "stop", "log_id": str(log_id)}}
        except Exception as exc:
            logger.exception("Corrective RAG stream error")
            await _write_query_log(
                self.db,
                log_id=log_id,
                query=query,
                faithfulness=None,
                had_context=False,
                latency_ms=_latency_ms(),
            )
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {"finish_reason": "error", "log_id": str(log_id)}}

    def _generate_draft(self, query: str, context_block: str) -> str:
        """Context'ten taslak cevap üretir (non-streaming)."""
        messages = [
            SystemMessage(SYSTEM_PROMPT),
            HumanMessage(build_user_prompt(query, context_block)),
        ]
        response = self._llm().invoke(messages, config=callback_config())
        return str(getattr(response, "content", ""))
