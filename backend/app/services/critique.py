"""Self-critique / corrective RAG yardımcıları.

Proaktif doğruluk mekanizması: context yetersizse sorgu yeniden yazılır
(rewrite_query), üretilen taslak cevap LLM tarafından eleştirilip gerekirse
düzeltilir (critique_answer). Gerçek LLM çağrısı yapılır; testler get_llm'i
mock'lar.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
from app.core.observability import callback_config
from app.services.verification import _parse_json_response

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = (
    "Sen bir arama sorgusu iyileştiricisisin. Mevcut context bir soruya cevap "
    "vermek için yetersiz kaldığında, aynı bilgi ihtiyacını daha iyi karşılayacak "
    "şekilde sorguyu yeniden yazarsın. Yalnızca yeni sorguyu döndürürsün; "
    "açıklama, başlık veya işaret eklemezsin."
)

_CRITIQUE_SYSTEM = (
    "Sen titiz bir cevap eleştirmenisin. Cevabın, verilen context'e dayanarak "
    "soruyu tam ve doğru yanıtlayıp yanıtlamadığını denetler, gerekirse cevabı "
    "düzeltirsin. Context'te olmayan hiçbir bilgiyi eklemezsin."
)


def rewrite_query(original_query: str, failed_context: list[dict]) -> str:
    """Yetersiz context için sorguyu yeniden yazar; yalnızca yeni sorgu döner.

    LLM boş çıktı verirse orijinal sorgu döner (savunmacı: arama asla bozulmaz).
    """
    context_block = (
        "\n".join(str(c.get("content", ""))[:800] for c in failed_context) or "(hiç sonuç yok)"
    )
    prompt = (
        f"ORİJİNAL SORU: {original_query}\n\n"
        f"YETERSİZ CONTEXT:\n{context_block}\n\n"
        "Bu soruya mevcut context yetersiz. Daha iyi bir arama yapmak için bu "
        "soruyu nasıl yeniden yazarsın? Sadece yeni soruyu dön."
    )
    response = get_llm().invoke(
        [SystemMessage(_REWRITE_SYSTEM), HumanMessage(prompt)], config=callback_config()
    )
    rewritten = str(getattr(response, "content", "")).strip().strip('"').strip("'")
    return rewritten or original_query


def critique_answer(query: str, draft_answer: str, context: str) -> dict:
    """Taslak cevabı context'e karşı eleştirir; gerekirse düzeltilmiş cevap döner.

    LLM'den JSON beklenir: {"is_satisfactory": bool, "critique": str,
    "revised_answer": str}. Dönüş aynı alanları taşır.
    """
    prompt = (
        f"SORU: {query}\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"TASLAK CEVAP:\n{draft_answer}\n\n"
        "Bu cevap, verilen context'e dayanarak soruyu tam ve doğru yanıtlıyor mu? "
        "Eğer hayırsa, cevabı düzelt. SADECE şu formatta JSON dön: "
        '{"is_satisfactory": <true/false>, "critique": "...", "revised_answer": "..."}'
    )
    response = get_llm().invoke(
        [SystemMessage(_CRITIQUE_SYSTEM), HumanMessage(prompt)], config=callback_config()
    )
    data: dict[str, Any] = _parse_json_response(getattr(response, "content", str(response)))
    return {
        "is_satisfactory": bool(data.get("is_satisfactory")),
        "critique": str(data.get("critique", "")),
        "revised_answer": str(data.get("revised_answer", draft_answer)) or draft_answer,
    }
