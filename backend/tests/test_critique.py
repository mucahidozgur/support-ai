"""Self-critique / corrective RAG testleri (LLM ve retrieval mock'lanır)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat import INSUFFICIENT_CONTEXT_ANSWER, CorrectiveChatService
from app.services.critique import critique_answer, rewrite_query

CORRECTIVE_URL = "/api/ai/chat/corrective"

SUFFICIENT_CHUNKS = [
    {
        "chunk_id": uuid4(),
        "document_id": uuid4(),
        "document_title": "Rehber",
        "content": "Kurulum paketleri indirilir.",
        "similarity": 0.8,
        "chunk_index": 0,
    }
]

INSUFFICIENT_CHUNKS = [
    {
        "chunk_id": uuid4(),
        "document_id": uuid4(),
        "document_title": "Zayıf",
        "content": "alakasız içerik",
        "similarity": 0.2,
        "chunk_index": 0,
    }
]


class _SeqLLM:
    """invoke çağrılarını sırayla verilen yanıtlarla cevaplayan sahte model."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list = []

    def invoke(self, messages, config=None, **kwargs) -> SimpleNamespace:
        self.calls.append(messages)
        return SimpleNamespace(content=self.responses.pop(0))

    async def astream(self, messages, config=None, **kwargs):  # pragma: no cover
        raise NotImplementedError


def test_rewrite_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM yeni sorgu döndürür; boş dönerse orijinal sorgu korunur."""
    fake = _SeqLLM(["yeniden yazılmış soru?"])
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    assert rewrite_query("orijinal soru?", INSUFFICIENT_CHUNKS) == "yeniden yazılmış soru?"

    empty = _SeqLLM(["   "])
    monkeypatch.setattr("app.services.critique.get_llm", lambda: empty)
    assert rewrite_query("orijinal soru?", []) == "orijinal soru?"


def test_critique_answer_satisfactory(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_satisfactory=true dönünce eleştiri sonucu satisfactory olur."""
    fake = _SeqLLM(
        ['{"is_satisfactory": true, "critique": "cevap yeterli", "revised_answer": "aynı"}']
    )
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    result = critique_answer("soru?", "taslak cevap.", "context metni")
    assert result["is_satisfactory"] is True
    assert result["critique"] == "cevap yeterli"


async def test_critique_answer_needs_revision_used_in_flow(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """is_satisfactory=false iken akış düzeltilmiş cevabı kullanır (revision event'i)."""
    fake = _SeqLLM(
        [
            "taslak cevap.",  # draft
            # 1. critique: eksik → revision
            '{"is_satisfactory": false, "critique": "eksik", "revised_answer": "düzeltilmiş cevap."}',
            # 2. critique (retry): düzeltilmiş cevap artık yeterli
            '{"is_satisfactory": true, "critique": "tamam", "revised_answer": "düzeltilmiş cevap."}',
        ]
    )
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    async def fake_retrieval(self, query, limit=3, **kwargs):
        return SUFFICIENT_CHUNKS

    monkeypatch.setattr("app.services.rag.RAGService.search_hybrid_rerank", fake_retrieval)
    service = CorrectiveChatService(db_session, uuid4())
    events = [e async for e in service.corrective_rag_stream("soru?", max_retries=2)]

    names = [e["event"] for e in events]
    assert "revision" in names
    assert "rewrite" not in names  # context yeterliydi
    token = next(e["data"]["text"] for e in events if e["event"] == "token")
    assert token == "düzeltilmiş cevap."
    assert events[-1]["data"]["finish_reason"] == "stop"


async def test_corrective_rag_no_rewrite_needed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yeterli context varsa rewrite atlanır, taslak cevap aynen stream edilir."""
    fake = _SeqLLM(
        [
            "taslak cevap.",
            '{"is_satisfactory": true, "critique": "iyi", "revised_answer": "taslak cevap."}',
        ]
    )
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    async def fake_retrieval(self, query, limit=3, **kwargs):
        return SUFFICIENT_CHUNKS

    monkeypatch.setattr("app.services.rag.RAGService.search_hybrid_rerank", fake_retrieval)
    service = CorrectiveChatService(db_session, uuid4())
    events = [e async for e in service.corrective_rag_stream("soru?", max_retries=2)]

    names = [e["event"] for e in events]
    assert "rewrite" not in names
    assert "critique" in names
    token = next(e["data"]["text"] for e in events if e["event"] == "token")
    assert token == "taslak cevap."


async def test_corrective_rag_rewrite_triggered(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yetersiz context'te rewrite tetiklenir ve yeni sorguyla arama tekrarlanır."""
    fake = _SeqLLM(
        [
            "yeniden yazılmış soru?",  # rewrite
            "taslak cevap.",  # draft
            '{"is_satisfactory": true, "critique": "iyi", "revised_answer": "taslak cevap."}',
        ]
    )
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    retrieval_calls: list = []

    async def fake_retrieval(self, query, limit=3, **kwargs):
        retrieval_calls.append(query)
        return SUFFICIENT_CHUNKS if len(retrieval_calls) > 1 else INSUFFICIENT_CHUNKS

    monkeypatch.setattr("app.services.rag.RAGService.search_hybrid_rerank", fake_retrieval)
    service = CorrectiveChatService(db_session, uuid4())
    events = [e async for e in service.corrective_rag_stream("soru?", max_retries=2)]

    names = [e["event"] for e in events]
    assert "rewrite" in names
    rewrite = next(e["data"] for e in events if e["event"] == "rewrite")
    assert rewrite == {"original_query": "soru?", "new_query": "yeniden yazılmış soru?"}
    assert retrieval_calls == ["soru?", "yeniden yazılmış soru?"]


async def test_corrective_rag_still_insufficient(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rewrite sonrası da yetersizse sabit bilgi-yok cevabı döner (LLM draft yok)."""
    fake = _SeqLLM(["yeniden yazılmış soru?"])
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    async def fake_retrieval(self, query, limit=3, **kwargs):
        return INSUFFICIENT_CHUNKS

    monkeypatch.setattr("app.services.rag.RAGService.search_hybrid_rerank", fake_retrieval)
    service = CorrectiveChatService(db_session, uuid4())
    events = [e async for e in service.corrective_rag_stream("soru?", max_retries=2)]

    names = [e["event"] for e in events]
    assert "rewrite" in names
    assert "critique" not in names  # taslak üretilmedi
    token = next(e["data"]["text"] for e in events if e["event"] == "token")
    assert token == INSUFFICIENT_CONTEXT_ANSWER
    assert events[-1]["data"]["insufficient_context"] is True
    # LLM'den yalnızca rewrite çağrıldı (draft için invoke yok).
    assert len(fake.calls) == 1


def test_corrective_endpoint(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint SSE formatında stream eder (rewrite içermeyen mutlu yol)."""
    fake = _SeqLLM(
        [
            "taslak cevap.",
            '{"is_satisfactory": true, "critique": "iyi", "revised_answer": "taslak cevap."}',
        ]
    )
    monkeypatch.setattr("app.services.chat.get_llm", lambda: fake)
    monkeypatch.setattr("app.services.critique.get_llm", lambda: fake)

    async def fake_retrieval(self, query, limit=3, **kwargs):
        return SUFFICIENT_CHUNKS

    monkeypatch.setattr("app.services.rag.RAGService.search_hybrid_rerank", fake_retrieval)
    with app_client.stream(
        "POST", CORRECTIVE_URL, json={"query": "soru?"}, headers=auth_headers
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = resp.read().decode("utf-8")
    assert "event: token" in raw
    assert "event: critique" in raw
    assert "event: done" in raw


def test_corrective_endpoint_requires_auth(app_client: TestClient) -> None:
    """Token'sız corrective isteği reddedilir."""
    resp = app_client.post(CORRECTIVE_URL, json={"query": "soru?"})
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401
