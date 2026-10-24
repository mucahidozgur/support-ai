"""Citation doğrulama + hallucination tespiti.

Müşterinin kalp şartı: her cevap kaynağa bağlanmalı (chunk_id), kaynaksız
cümle işaretlenmeli, cevap context'e sadık değilse hallucination sayılmalı.
Gerçek LLM (Groq) çağrıları yapılır; testler `get_llm`'i mock'lar.
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
from app.core.observability import callback_config, observe_rag, update_observation_output

logger = logging.getLogger(__name__)

# Bu skorun altındaki faithfulness cevapları hallucination sayılır.
HALLUCINATION_THRESHOLD = 0.7

_VERIFY_SYSTEM = (
    "Sen bir kaynak doğrulayıcısısın. Verilen her cümle için, cümleyi destekleyen "
    "kaynağın chunk_id'sini döndürürsün; hiçbir kaynak desteklemiyorsa 'NONE' dersin. "
    "Asla kaynaklarda olmayan bilgiyi destekli sayma."
)

_FAITHFULNESS_SYSTEM = (
    "Sen bir doğruluk denetçisisin. Cevabın, verilen kaynaklara ne kadar sadık "
    "olduğunu 0.0 (tamamen uydurma) ile 1.0 (tamamen sadık) arasında puanlarsın."
)


def _split_sentences(text: str) -> list[str]:
    """Metni cümle sınırlarından böler ([.!?] + boşluk)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sources_block(sources: list[dict]) -> str:
    """Kaynakları LLM promptu için numaralı blok haline getirir."""
    lines = []
    for i, source in enumerate(sources):
        content = str(source.get("content", ""))[:1500]
        lines.append(f"[{i + 1}] chunk_id={source.get('chunk_id')}: {content}")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> dict[str, Any]:
    """LLM çıktısını JSON'a çevirir (```json bloklarını ayıklar)."""
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if not match:
            raise ValueError("LLM çıktısı JSON olarak çözülemedi") from None
        data = json.loads(match.group(1))
    if not isinstance(data, dict):
        # LLM çıktısının formatı (çağıranın argüman tipi değil) → ValueError.
        raise ValueError("LLM çıktısı nesne değil")  # noqa: TRY004
    return data


@observe_rag("verify_citations")
def verify_citations(answer: str, sources: list[dict]) -> dict:
    """Cevabın her cümlesini kaynaklara karşı doğrular.

    Her cümle için LLM, destekleyen kaynağın chunk_id'sini (veya "NONE") döner.
    Kaynak listesinde olmayan chunk_id'ler NONE sayılır (LLM'in uydurduğu
    citation kabul edilmez). Dönüş: {"sentences", "verified",
    "unsupported_sentences"}.
    """
    sentences = _split_sentences(answer)
    if not sentences:
        return {"sentences": [], "verified": True, "unsupported_sentences": []}

    prompt = (
        "Aşağıdaki her cümle için, o cümleyi destekleyen kaynağın chunk_id'sini dön; "
        'hiçbir kaynak desteklemiyorsa "NONE" dön. '
        'SADECE şu formatta JSON dön: {"results": {"0": "<chunk_id veya NONE>", ...}}\n\n'
        f"KAYNAKLAR:\n{_sources_block(sources)}\n\n"
        "CÜMLELER:\n" + "\n".join(f"{i}: {s}" for i, s in enumerate(sentences))
    )
    response = get_llm().invoke(
        [SystemMessage(_VERIFY_SYSTEM), HumanMessage(prompt)], config=callback_config()
    )
    data = _parse_json_response(getattr(response, "content", str(response)))
    results = data.get("results")
    if not isinstance(results, dict):
        # LLM çıktısının formatı (çağıranın argüman tipi değil) → ValueError.
        raise ValueError("LLM çıktısında 'results' nesnesi yok")  # noqa: TRY004

    valid_ids = {source.get("chunk_id") for source in sources}
    supported: list[dict] = []
    unsupported: list[str] = []
    for index, sentence in enumerate(sentences):
        chunk_id = str(results.get(str(index), "NONE")).strip()
        if chunk_id == "NONE" or chunk_id not in valid_ids:
            unsupported.append(sentence)
            chunk_id = "NONE"
        supported.append({"text": sentence, "supported_by": chunk_id})

    update_observation_output({"verified": not unsupported, "unsupported_count": len(unsupported)})
    return {
        "sentences": supported,
        "verified": not unsupported,
        "unsupported_sentences": unsupported,
    }


def detect_hallucination(answer: str, sources: list[dict]) -> dict:
    """Cevabın context'e sadakatini 0-1 skorlar (hafif faithfulness).

    LLM'den JSON {"score": float, "reasoning": str} beklenir. Skor eşiğin
    (0.7) altındaysa is_hallucination=True döner.
    """
    prompt = (
        "Bu cevap, aşağıdaki kaynaklara tamamen sadık mı? 0.0 (tamamen uydurma) ile "
        "1.0 (tamamen sadık) arasında puan ver ve nedenini kısaca açıkla. "
        'SADECE şu formatta JSON dön: {"score": <0-1>, "reasoning": "..."}\n\n'
        f"KAYNAKLAR:\n{_sources_block(sources)}\n\n"
        f"CEVAP:\n{answer}"
    )
    response = get_llm().invoke(
        [SystemMessage(_FAITHFULNESS_SYSTEM), HumanMessage(prompt)], config=callback_config()
    )
    data = _parse_json_response(getattr(response, "content", str(response)))
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        raise ValueError("LLM çıktısında geçerli 'score' yok") from None
    score = max(0.0, min(1.0, score))
    return {
        "faithfulness": score,
        "reasoning": str(data.get("reasoning", "")),
        "is_hallucination": score < HALLUCINATION_THRESHOLD,
    }
