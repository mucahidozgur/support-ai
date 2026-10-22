"""Agent state tanımı: LangGraph graph'ı boyunca taşınan veri."""

from typing import Literal, TypedDict
from uuid import UUID

RouteIntent = Literal["qa", "summarize", "extract_actions", "compare"]


class AgentState(TypedDict, total=False):
    """Agent akışındaki adımlar arasında paylaşılan state."""

    # Girdi
    query: str
    owner_id: str
    # Not: endpoint pydantic aracılığıyla UUID'ye çevirir; str de tolere edilir.
    document_ids: list[UUID] | None
    top_k: int

    # Router çıktısı
    intent: RouteIntent

    # Retrieval / tool çıktıları
    chunks: list[dict]  # qa için
    sources: list[dict]  # frontend'e gönderilecek kaynak listesi
    tool_output: str  # summarize/extract_actions/compare çıktısı

    # Tool node'larının hazırladığı prompt'lar (LLM streaming bunlarla yapılır)
    system_prompt: str
    user_prompt: str

    # Final
    answer: str
    error: str | None
