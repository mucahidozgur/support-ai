"""Chat servisi: RAG context'i ile SSE streaming yanıt üretir.

Akış: hybrid+rerank arama → güven eşiği kontrolü → LLM stream →
citation doğrulaması + hallucination tespiti (verification event'i).
"""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.schemas.ai import ChatSource
from app.services.prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt
from app.services.rag import RAGService, has_sufficient_context
from app.services.verification import detect_hallucination, verify_citations

logger = logging.getLogger(__name__)

INSUFFICIENT_CONTEXT_ANSWER = (
    "Bu bilgi knowledge base'de bulunmuyor. Lütfen ilgili dokümanı kontrol edin "
    "veya uzmanınıza danışın."
)


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
        edilir ve done event'i insufficient_context=true taşır.
        """
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
                yield {
                    "event": "done",
                    "data": {"finish_reason": "insufficient_context", "insufficient_context": True},
                }
                return

            sources = [ChatSource.model_validate(chunk).model_dump(mode="json") for chunk in chunks]
            yield {"event": "sources", "data": sources}

            context_block = build_context_block(chunks)
            messages = [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(build_user_prompt(query, context_block)),
            ]
            answer_parts: list[str] = []
            async for chunk in self._llm().astream(messages):
                if chunk.content:
                    answer_parts.append(chunk.content)
                    yield {"event": "token", "data": {"text": chunk.content}}

            if verify:
                yield await self._verification_event(query, chunks, "".join(answer_parts))
            yield {"event": "done", "data": {"finish_reason": "stop"}}
        except Exception as exc:
            logger.exception("Chat stream error")
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {"finish_reason": "error"}}

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
