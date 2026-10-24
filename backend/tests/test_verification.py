"""Citation doğrulama + hallucination tespiti testleri (LLM mock'lanır)."""

from types import SimpleNamespace

import pytest

from app.services.rag import has_sufficient_context
from app.services.verification import detect_hallucination, verify_citations

SOURCES = [
    {"chunk_id": "chunk-a", "content": "Kurulum paketleri indirilir."},
    {"chunk_id": "chunk-b", "content": "Port 443 açık olmalıdır."},
]


class _FakeLLM:
    """invoke'u önceden belirlenmiş içerikle yanıtlayan sahte model."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list = []

    def invoke(self, messages) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.response)


def test_verify_citations_all_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tüm cümleler geçerli kaynaklarla desteklenince verified=True döner."""
    fake = _FakeLLM('{"results": {"0": "chunk-a", "1": "chunk-b"}}')
    monkeypatch.setattr("app.services.verification.get_llm", lambda: fake)

    result = verify_citations("Paketler indirilir. Port 443 açık.", SOURCES)
    assert result["verified"] is True
    assert result["unsupported_sentences"] == []
    assert [s["supported_by"] for s in result["sentences"]] == ["chunk-a", "chunk-b"]


def test_verify_citations_some_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bir cümle NONE dönünce verified=False ve cümle listelenir."""
    fake = _FakeLLM('{"results": {"0": "chunk-a", "1": "NONE"}}')
    monkeypatch.setattr("app.services.verification.get_llm", lambda: fake)

    result = verify_citations("Paketler indirilir. Ay'da tavşan var.", SOURCES)
    assert result["verified"] is False
    assert result["unsupported_sentences"] == ["Ay'da tavşan var."]


def test_verify_citations_unknown_id_treated_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM'in uydurduğu (kaynaklarda olmayan) chunk_id NONE sayılır."""
    fake = _FakeLLM('{"results": {"0": "uydurma-id"}}')
    monkeypatch.setattr("app.services.verification.get_llm", lambda: fake)

    result = verify_citations("Paketler indirilir.", SOURCES)
    assert result["verified"] is False
    assert result["sentences"][0]["supported_by"] == "NONE"


def test_detect_hallucination_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faithfulness < 0.7 → is_hallucination=True."""
    fake = _FakeLLM('{"score": 0.5, "reasoning": "Cevap yarı yarıya uydurma."}')
    monkeypatch.setattr("app.services.verification.get_llm", lambda: fake)

    result = detect_hallucination("Uydurma cevap.", SOURCES)
    assert result["faithfulness"] == pytest.approx(0.5)
    assert result["reasoning"] == "Cevap yarı yarıya uydurma."
    assert result["is_hallucination"] is True


def test_detect_hallucination_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faithfulness ≥ 0.7 → is_hallucination=False."""
    fake = _FakeLLM('{"score": 0.9, "reasoning": "Cevap kaynaklara sadık."}')
    monkeypatch.setattr("app.services.verification.get_llm", lambda: fake)

    result = detect_hallucination("Sadık cevap.", SOURCES)
    assert result["is_hallucination"] is False


def test_has_sufficient_context() -> None:
    """Eşik üstü True, altı False, boş liste False döner."""
    assert has_sufficient_context([{"similarity": 0.6}]) is True
    assert has_sufficient_context([{"similarity": 0.3, "x": 1}, {"similarity": 0.9}]) is True
    assert has_sufficient_context([{"similarity": 0.3}]) is False
    assert has_sufficient_context([]) is False
    # Özel eşik parametresi
    assert has_sufficient_context([{"similarity": 0.5}], min_similarity=0.4) is True
