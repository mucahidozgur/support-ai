"""Hiyerarşik chunking + parent retrieval (expand_context) testleri."""

from fastapi.testclient import TestClient

from app.services.chunking import chunk_text_hierarchical

DOCS_URL = "/api/documents"
HYBRID_URL = "/api/ai/search/hybrid"

MARKDOWN_TEXT = """# Kurulum
Bu rehber sistemi kurmayı anlatır.

## Gereksinimler
Sunucu ve ağ gereksinimleri listelenir.

### Ağ
Port 443 açık olmalıdır.

## Adım Adım Kurulum
Paketleri indirin, yapılandırın ve doğrulayın."""


def _expand_text() -> str:
    """Tek `# Kurulum Rehberi` bölümü altında 8 uzun paragraf üretir.

    Bölüm 1000 karakter sınırı yüzünden birden çok chunk'a bölünür; hepsi aynı
    heading'i taşır ve hepsinde "kurulum" kelimesi geçer.
    """
    paragraphs = []
    for i in range(8):
        sentence = (
            f"Kurulum adımı {i}: sunucu hazırlığı yapılır, kurulum paketleri indirilir "
            "ve yapılandırma dosyaları düzenlenir. Kurulum doğrulaması için test "
            "komutu çalıştırılır. "
        )
        paragraphs.append(sentence * 4)
    return "# Kurulum Rehberi\n\n" + "\n\n".join(paragraphs)


class _FakeReranker:
    """predict'i verilen skor listesiyle yanıtlayan sahte cross-encoder."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[int] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(len(pairs))
        return self.scores[: len(pairs)]


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


def test_chunk_text_hierarchical_basic() -> None:
    """Başlıklı metin hiyerarşiye göre bölünür; heading zinciri doğru atanır."""
    chunks = chunk_text_hierarchical(MARKDOWN_TEXT)
    assert [c["heading"] for c in chunks] == [
        "Kurulum",
        "Kurulum > Gereksinimler",
        "Kurulum > Gereksinimler > Ağ",
        "Kurulum > Adım Adım Kurulum",
    ]
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2, 3]
    # Content, heading prefix'i ile başlar (chunk tek başına anlamlı olsun).
    assert chunks[0]["content"].startswith("Kurulum\nBu rehber")
    assert chunks[2]["content"].startswith("Kurulum > Gereksinimler > Ağ\nPort 443")


def test_chunk_text_hierarchical_no_headings() -> None:
    """Başlıksız metin paragraflara göre bölünür; heading None olur."""
    text = "İlk paragraf içeriği.\n\nİkinci paragraf içeriği.\n\nÜçüncü paragraf içeriği."
    chunks = chunk_text_hierarchical(text)
    assert len(chunks) == 3
    assert all(c["heading"] is None for c in chunks)
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2]


def test_chunk_text_hierarchical_splits_long_sections() -> None:
    """Uzun bölüm alt chunk'lara ayrılır; hepsi aynı heading'i taşır."""
    text = "# Bölüm\n" + "uzun içerik cümlesi. " * 60
    chunks = chunk_text_hierarchical(text, max_chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(c["heading"] == "Bölüm" for c in chunks)
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_expand_context(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    """expand_context=True: rerank top-k'ya ek olarak aynı başlıktaki chunk'lar döner."""
    fake = _FakeReranker([1.0 - 0.01 * i for i in range(20)])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    _create_and_index(app_client, auth_headers, "Kurulum Dokümanı", _expand_text())

    resp = app_client.post(
        HYBRID_URL,
        json={
            "query": "kurulum",
            "limit": 3,
            "alpha": 0.0,
            "rerank_candidates": 20,
            "expand_context": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) > 3  # rerank top-3 + bağlam genişletmesi
    assert results[0]["heading"] == "Kurulum Rehberi"
    expanded = [r for r in results if r["expanded"]]
    assert expanded
    assert all(r["heading"] == results[0]["heading"] for r in expanded)
    # Rerank edilen ilk 3'te expanded işareti yok; tekrar yok (dedupe).
    assert all(not r["expanded"] for r in results[:3])
    chunk_ids = [r["chunk_id"] for r in results]
    assert len(chunk_ids) == len(set(chunk_ids))


def test_expand_context_false_returns_reranked_only(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    """expand_context=False (varsayılan): yalnızca rerank top-k döner."""
    fake = _FakeReranker([1.0 - 0.01 * i for i in range(20)])
    monkeypatch.setattr("app.services.rag.get_reranker", lambda: fake)
    _create_and_index(app_client, auth_headers, "Kurulum Dokümanı", _expand_text())

    resp = app_client.post(
        HYBRID_URL,
        json={"query": "kurulum", "limit": 3, "alpha": 0.0, "rerank_candidates": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3
    assert all(not r["expanded"] for r in results)


def test_expand_context_requires_rerank(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """expand_context, use_rerank=False ile istenirse → 400."""
    resp = app_client.post(
        HYBRID_URL,
        json={"query": "kurulum", "use_rerank": False, "expand_context": True},
        headers=auth_headers,
    )
    assert resp.status_code == 400
