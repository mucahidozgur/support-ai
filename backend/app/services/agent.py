"""Agent servisi: LangGraph (router + retrieve) çalıştırır ve SSE event'leri üretir."""

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import AGENT_GRAPH
from app.core.llm import get_llm
from app.services.prompts import SYSTEM_PROMPT, build_context_block, build_user_prompt

logger = logging.getLogger(__name__)


class AgentService:
    """LangGraph tabanlı çok adımlı agent; qa yolu SSE ile stream edilir."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.llm = get_llm()

    async def stream_agent(
        self,
        query: str,
        document_ids: list[UUID] | None = None,
        top_k: int = 5,
    ) -> AsyncIterator[dict[str, object]]:
        """LangGraph'ı çalıştırır ve SSE event dict'leri üretir.

        Event'ler: intent, sources, token, done, error.
        Tüm 4 yol (qa, summarize, extract_actions, compare) aynı streaming
        noktasından geçer; fark, node'ların hazırladığı prompt'lardadır.
        """
        try:
            state = {
                "query": query,
                "owner_id": str(self.owner_id),
                "document_ids": document_ids,
                "top_k": top_k,
            }
            result = await AGENT_GRAPH.ainvoke(state, config={"configurable": {"db": self.db}})

            # 1) intent event'i
            yield {"event": "intent", "data": {"intent": result["intent"]}}

            # 2) hata kontrolü (tool node'larının error alanı)
            if result.get("error"):
                yield {"event": "error", "data": {"message": result["error"]}}
                yield {"event": "done", "data": {"finish_reason": "error"}}
                return

            # 3) sources event'i (içerik hariç — metadata frontend için yeterli)
            if result.get("chunks"):
                yield {
                    "event": "sources",
                    "data": [
                        {k: v for k, v in c.items() if k != "content"} for c in result["chunks"]
                    ],
                }

            # 4) tool prompt'ları varsa onları, yoksa qa prompt'larını kullan
            system_prompt = result.get("system_prompt") or SYSTEM_PROMPT
            user_prompt = result.get("user_prompt") or build_user_prompt(
                state["query"], build_context_block(result.get("chunks", []))
            )

            # 5) LLM streaming (tek nokta)
            async for chunk in self.llm.astream(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            ):
                if chunk.content:
                    yield {"event": "token", "data": {"text": chunk.content}}

            yield {"event": "done", "data": {"finish_reason": "stop"}}
        except Exception as exc:
            logger.exception("Agent stream error")
            yield {"event": "error", "data": {"message": str(exc)}}
            yield {"event": "done", "data": {"finish_reason": "error"}}
