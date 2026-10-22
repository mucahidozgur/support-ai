"""Agent node'ları: router, retrieve ve uzman tool node'ları (prompt hazırlama)."""

import logging
from uuid import UUID

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from app.agent.state import AgentState
from app.core.llm import get_llm
from app.services.prompts import (
    COMPARE_SYSTEM,
    EXTRACT_ACTIONS_SYSTEM,
    SUMMARIZE_SYSTEM,
    build_compare_user_prompt,
    build_extract_actions_user_prompt,
    build_summarize_user_prompt,
)
from app.services.rag import RAGService

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """Aşağıdaki kullanıcı sorgusunu tam olarak BİR kelimeyle sınıflandır:
- "qa": doküman hakkında bilgi sorusu (örn: "X nedir?", "Y'nin maddeleri?")
- "summarize": tek bir dokümanı özetleme isteği (örn: "bu dokümanı özetle")
- "extract_actions": aksiyon maddeleri çıkarma (örn: "yapılacakları çıkar")
- "compare": iki dokümanı karşılaştırma (örn: "A ile B'yi karşılaştır")

SADECE kelimeyi döndür, başka hiçbir şey yazma.
Sorgu: {query}
Sınıf:"""

VALID_INTENTS: set[str] = {"qa", "summarize", "extract_actions", "compare"}


async def router_node(state: AgentState) -> dict[str, str]:
    """Sorgunun niyetini sınıflandırır; bilinmeyen/hata durumunda "qa" fallback."""
    query = state["query"]
    try:
        # Router cevabı kısa olmalı; max_tokens=10 ile tek kelimeye zorlanır.
        response = (
            await get_llm()
            .bind(max_tokens=10)
            .ainvoke([HumanMessage(ROUTER_PROMPT.format(query=query))])
        )
        intent = str(response.content).strip().lower().split()[0]
    except Exception:
        logger.exception("Router LLM hatası; qa'ya fallback")
        return {"intent": "qa"}
    return {"intent": intent if intent in VALID_INTENTS else "qa"}


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    """Intent'e göre retrieval yapar; chunks ve sources'ı state'e doldurur.

    - qa: sorguyla semantik arama (top_k chunk)
    - summarize/extract_actions: ilk dokümanın TÜM chunk'ları
    - compare: ilk 2 dokümanın TÜM chunk'ları
    """
    db = config["configurable"]["db"]
    owner_id = UUID(state["owner_id"])
    # Pydantic document_ids'i UUID'ye çevirmiş olabilir; str gelirse cast et.
    document_ids = [d if isinstance(d, UUID) else UUID(d) for d in state.get("document_ids") or []]
    rag = RAGService(db, owner_id)
    intent = state.get("intent", "qa")

    if intent == "qa":
        chunks = await rag.search(state["query"], document_ids or None, limit=state.get("top_k", 5))
    elif intent in ("summarize", "extract_actions"):
        # Doküman seçilmediyse boş liste — tool node'u error üretir.
        chunks = await rag.get_all_chunks(document_ids[0]) if document_ids else []
    else:  # compare
        chunks = []
        for doc_id in document_ids[:2]:
            chunks.extend(await rag.get_all_chunks(doc_id))
    return {"chunks": chunks, "sources": chunks}


async def qa_node(state: AgentState) -> dict[str, str]:
    """Placeholder: streaming'i endpoint halleder; context hazırlığı orada."""
    return {"answer": ""}


def _chunks_of_first_document(chunks: list[dict]) -> list[dict]:
    """Chunk listesini ilk document_id'ye ait olanlarla filtreler."""
    if not chunks:
        return []
    first_doc_id = chunks[0]["document_id"]
    return [c for c in chunks if c["document_id"] == first_doc_id]


async def summarize_node(state: AgentState) -> dict[str, str]:
    """İlk dokümanın chunk'ları için özet prompt'larını hazırlar."""
    chunks = _chunks_of_first_document(state.get("chunks", []))
    if not chunks:
        return {"error": "Özetlemek için doküman bulunamadı"}
    return {
        "system_prompt": SUMMARIZE_SYSTEM,
        "user_prompt": build_summarize_user_prompt(chunks),
    }


async def extract_actions_node(state: AgentState) -> dict[str, str]:
    """İlk dokümanın chunk'ları için aksiyon çıkarma prompt'larını hazırlar."""
    chunks = _chunks_of_first_document(state.get("chunks", []))
    if not chunks:
        return {"error": "Aksiyon çıkarmak için doküman bulunamadı"}
    return {
        "system_prompt": EXTRACT_ACTIONS_SYSTEM,
        "user_prompt": build_extract_actions_user_prompt(chunks),
    }


async def compare_node(state: AgentState) -> dict[str, str]:
    """İlk 2 dokümanın chunk'ları için karşılaştırma prompt'larını hazırlar."""
    document_ids = state.get("document_ids") or []
    if len(document_ids) < 2:
        return {"error": "Karşılaştırma için en az 2 doküman seçmelisiniz"}
    id_a, id_b = str(document_ids[0]), str(document_ids[1])
    chunks_a = [c for c in state.get("chunks", []) if str(c["document_id"]) == id_a]
    chunks_b = [c for c in state.get("chunks", []) if str(c["document_id"]) == id_b]
    if not chunks_a or not chunks_b:
        return {"error": "Karşılaştırma için iki dokümanın içeriği bulunamadı"}
    return {
        "system_prompt": COMPARE_SYSTEM,
        "user_prompt": build_compare_user_prompt(chunks_a, chunks_b),
    }


def route_after_router(state: AgentState) -> str:
    """Router sonrası koşullu yönlendirme: intent'e göre node seçer."""
    return state.get("intent", "qa")
