"""AI endpoint'leri: RAG arama ve SSE streaming chat."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.db import get_db
from app.schemas.ai import ChatRequest, SearchRequest, SearchResponse
from app.schemas.auth import UserInfo
from app.services.agent import AgentService
from app.services.chat import ChatService
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


@router.post("/chat")
async def chat(body: ChatRequest, db: DbDep, current_user: UserDep) -> EventSourceResponse:
    """RAG context'i ile SSE streaming chat yanıtı döndürür."""
    owner_id = UUID(current_user.id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            service = ChatService(db, owner_id)
            async for event in service.stream_chat(body.query, body.document_ids, body.top_k):
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
