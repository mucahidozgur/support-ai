"""Hybrid arama (BM25 + vektör + RRF) testleri."""

import pytest
from fastapi.testclient import TestClient

from app.services.rag import rrf_fuse

DOCS_URL = "/api/documents"
HYBRID_URL = "/api/ai/search/hybrid"

# Tek chunk'a sığacak kadar kısa, birbirinden keskin biçimde farklı iki metin.
TECH_TEXT = """PostgreSQL full-text search uses tsvector and tsquery data types. The ts_rank
function scores documents by relevance to a query. A GIN index accelerates text search
queries. The websearch_to_tsquery function parses user input safely."""

FOOD_TEXT = """Mantı tarifi: hamur un, yumurta ve su ile yoğrulur. İç harcı kıyma ve soğandan
hazırlanır. Mantılar tuzlu suda haşlanır, sarımsaklı yoğurtla servis edilir. Yanında ayran
ikram edilir."""


def _headers_for(app_client: TestClient, username: str) -> dict[str, str]:
    """Verilen username için login olup Bearer header döndürür."""
    resp = app_client.post("/api/auth/login", json={"username": username, "password": "x"})
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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


def _item(chunk_id: str) -> dict:
    """rrf_fuse unit testi için minimal sonuç elemanı."""
    return {
        "chunk_id": chunk_id,
        "document_id": "doc",
        "document_title": "t",
        "content": chunk_id,
        "similarity": 0.9,
        "chunk_index": 0,
    }


def test_rrf_fuse() -> None:
    """RRF: iki listedeki skorlar toplanır ve toplama göre sıralanır.

    vektör: [a, b, c] (rank 1,2,3), bm25: [b, d] (rank 1,2) →
    b: 1/61 + 1/62 ≈ 0.0325 (both), a: 1/61 (vector), d: 1/62 (bm25), c: 1/63 (vector)
    """
    vector = [_item("a"), _item("b"), _item("c")]
    bm25 = [_item("b"), _item("d")]
    fused = rrf_fuse(vector, bm25, k=60)
    assert [r["chunk_id"] for r in fused] == ["b", "a", "d", "c"]
    assert fused[0]["similarity"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1]["similarity"] == pytest.approx(1 / 61)
    assert {r["chunk_id"]: r["retrieval_source"] for r in fused} == {
        "b": "both",
        "a": "vector",
        "d": "bm25",
        "c": "vector",
    }


def test_search_bm25_finds_keyword_chunk(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """alpha=0 (saf BM25): sorgudaki kelimeyi içeren chunk bulunur.

    "tsvector" kelimesi yalnızca TECH_TEXT'te geçtiği için tüm sonuçlar
    o dokümandan gelmeli ve retrieval_source == "bm25" olmalı.
    """
    tech_doc = _create_and_index(app_client, auth_headers, "FTS Guide", TECH_TEXT)
    _create_and_index(app_client, auth_headers, "Mantı Tarifi", FOOD_TEXT)
    resp = app_client.post(
        HYBRID_URL, json={"query": "tsvector", "alpha": 0.0}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert "tsvector" in results[0]["content"]
    assert all(r["document_id"] == tech_doc["id"] for r in results)
    assert all(r["retrieval_source"] == "bm25" for r in results)
    assert all(r["similarity"] > 0 for r in results)


def test_search_hybrid_combines_sources(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """alpha=0.5: her iki kaynağın da katkısı birleşir, sıra RRF skoruna göredir."""
    tech_doc = _create_and_index(app_client, auth_headers, "FTS Guide", TECH_TEXT)
    _create_and_index(app_client, auth_headers, "Mantı Tarifi", FOOD_TEXT)
    resp = app_client.post(
        HYBRID_URL, json={"query": "postgresql", "limit": 5, "alpha": 0.5}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    # Aynı chunk hem vektör hem BM25 listesinde: fusion'ın kanıtı.
    assert results[0]["retrieval_source"] == "both"
    assert results[0]["document_id"] == tech_doc["id"]
    assert all(r["retrieval_source"] in {"vector", "bm25", "both"} for r in results)
    scores = [r["similarity"] for r in results]
    assert scores == sorted(scores, reverse=True)  # RRF skoruna göre azalan


def test_search_hybrid_alpha_one_uses_only_vector(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """alpha=1: vektör araması tek başına çalışır."""
    tech_doc = _create_and_index(app_client, auth_headers, "FTS Guide", TECH_TEXT)
    _create_and_index(app_client, auth_headers, "Mantı Tarifi", FOOD_TEXT)
    resp = app_client.post(
        HYBRID_URL, json={"query": "postgresql", "alpha": 1.0}, headers=auth_headers
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert results[0]["document_id"] == tech_doc["id"]
    assert all(r["retrieval_source"] == "vector" for r in results)


def test_search_hybrid_limits_results(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """limit parametresi dönen sonuç sayısını sınırlar."""
    _create_and_index(app_client, auth_headers, "FTS Guide", TECH_TEXT)
    resp = app_client.post(
        HYBRID_URL, json={"query": "tsvector", "limit": 1, "alpha": 0.0}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_search_hybrid_empty_query(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Boş query → 422 (validation)."""
    resp = app_client.post(HYBRID_URL, json={"query": ""}, headers=auth_headers)
    assert resp.status_code == 422


def test_search_hybrid_invalid_alpha(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """alpha [0,1] dışındaysa → 422 (validation)."""
    resp = app_client.post(
        HYBRID_URL, json={"query": "tsvector", "alpha": 1.5}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_search_hybrid_requires_auth(app_client: TestClient) -> None:
    """Token'sız hybrid isteği reddedilir."""
    resp = app_client.post(HYBRID_URL, json={"query": "tsvector"})
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401
