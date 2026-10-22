"""Chat servisi: RAG context'i ile SSE streaming yanıt üretir."""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_llm
from app.schemas.ai import ChatSource
from app.services.prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt
from app.services.rag import RAGService

logger = logging.getLogger(__name__)


class ChatService:
    """RAG destekli chat: arama → prompt → LLM stream → SSE event'leri."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.rag = RAGService(db, owner_id)
        self.llm = get_llm()

    async def stream_chat(
        self,
        query: str,
        document_ids: list[UUID] | None = None,
        top_k: int = 5,
    ) -> AsyncIterator[dict[str, object]]:
        """SSE event dict'leri üretir: sources, token, done, error."""
        try:
            chunks = await self.rag.search(query, document_ids, limit=top_k)
            if not chunks:
                yield {
                    "event": "error",
                    "data": {"message": "Bu soruya cevap verebilecek bir doküman bulunamadı."},
                }
                yield {"event": "done", "data": {"finish_reason": "no_context"}}
                return

            sources = [ChatSource.model_validate(chunk).model_dump(mode="json") for chunk in chunks]
            yield {"event": "sources", "data": sources}

            context_block = build_context_block(chunks)
            messages = [
                SystemMessage(SYSTEM_PROMPT),
                HumanMessage(build_user_prompt(query, context_block)),
            ]
            async for chunk in self.llm.astream(messages):
                if chunk.content:
                    yield {"event": "token", "data": {"text": chunk.content}}
            yield {"event": "done", "data": {"finish_reason": "stop"}}
        except Exception as exc:
            logger.exception("Chat stream error")
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {"finish_reason": "error"}}
