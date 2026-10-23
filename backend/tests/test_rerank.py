"""Cross-encoder rerank testleri (gerçek model indirilmez — mock kullanılır)."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag import RAGService

DOCS_URL = "/api/documents"
HYBRID_URL = "/api/ai/search/hybrid"

BULK_N = 20  # rerank öncesi aday havuzu büyüklüğü


class _FakeReranker:
    """predict'i verilen skor listesiyle yanıtlayan sahte cross-encoder."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[int] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(len(pairs))
        return self.scores[: len(pairs)]


def _item(chunk_id: str) -> dict:
    """rerank unit testi için minimal aday elemanı."""
    return {"chunk_id": chunk_id, "content": f"içerik-{chunk_id}"}


def _bulk_content() -> str:
    """BULK_N adet ~750 karakterlik paragraf üretir; her biri tek chunk olur.

    Her paragrafta ortak "ortak" token'ı ve benzersiz "keywordNN" token'ı var.
    """
    paragraphs = []
    for i in range(BULK_N):
        body = " ".join([f"keyword{i:02d}"] * 70)  # ~700 karakter, chunk sınırı altında
        paragraphs.append(f"{i}. bölüm ortak konuyu anlatır. {body}")
    return "\n\n".join(paragraphs)


def _create_and_index(
    app_client: TestClient, headers: dict[str, str], title: str, content: str
) -> dict:
    """Yardımcı: doküman oluşturup index'ler, doküman body'sini döndürür."""
    created = app_client.post(DOCS_URL, json={"title": title, "content": content}, headers=headers)
    assert created.status_code == 201
    doc = created.json()
    indexed = app_client.post(f"{DOCS_URL}/{doc['id']}/index", headers=headers)
    assert indexed.status_code == 200
    return doc


async def test_rerank_orders_by_score(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rerank, model skoruna göre azalan sıralar; rerank_score ve similarity eşitlenir."""
    fake = _FakeReranker([0.2, 0.9, 0.5])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    service = RAGService(db_session, uuid4())

    ranked = await service.rerank("soru", [_item("a"), _item("b"), _item("c")], top_k=3)
    assert [r["chunk_id"] for r in ranked] == ["b", "c", "a"]
    assert [r["rerank_score"] for r in ranked] == [0.9, 0.5, 0.2]
    assert all(r["similarity"] == r["rerank_score"] for r in ranked)
    assert fake.calls == [3]

    # top_k sonuç sayısını sınırlar
    top2 = await service.rerank("soru", [_item("a"), _item("b"), _item("c")], top_k=2)
    assert [r["chunk_id"] for r in top2] == ["b", "c"]


async def test_rerank_empty_candidates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boş aday listesi hatasız [] döner; model hiç yüklenmez."""
    fake = _FakeReranker([])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    service = RAGService(db_session, uuid4())

    assert await service.rerank("soru", []) == []
    assert fake.calls == []


async def test_rerank_requires_content(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """content alanı olmayan aday ValueError üretir."""
    fake = _FakeReranker([])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    service = RAGService(db_session, uuid4())

    with pytest.raises(ValueError):
        await service.rerank("soru", [{"chunk_id": "x"}])
    assert fake.calls == []  # hata, model çağrılmadan fırlar


def test_search_hybrid_rerank(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint: 20 aday rerank'ten geçer, ilk 3'ü döner (rerank_score dolu)."""
    fake = _FakeReranker([1.0 - 0.01 * i for i in range(BULK_N)])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    _create_and_index(app_client, auth_headers, "Toplu Doküman", _bulk_content())

    resp = app_client.post(
        HYBRID_URL,
        json={"query": "ortak", "limit": 3, "alpha": 0.0, "rerank_candidates": BULK_N},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3  # 20 aday → 3 sonuç
    assert fake.calls == [BULK_N]  # rerank havuzun tamamını gördü
    assert all(r["rerank_score"] is not None for r in results)
    assert all(r["similarity"] == r["rerank_score"] for r in results)
    scores = [r["rerank_score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_hybrid_rerank_candidates_validation(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """rerank_candidates üst sınırı aşınca 422 (validation)."""
    resp = app_client.post(
        HYBRID_URL,
        json={"query": "ortak", "rerank_candidates": 51},
        headers=auth_headers,
    )
    assert resp.status_code == 422
