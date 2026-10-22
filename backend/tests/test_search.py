"""RAG arama endpoint testleri."""

from fastapi.testclient import TestClient

DOCS_URL = "/api/documents"
SEARCH_URL = "/api/ai/search"

PYTHON_TEXT = """Python is a high-level, general-purpose programming language. Its design
philosophy emphasizes code readability with the use of significant indentation. Python is
dynamically typed and garbage-collected. It supports multiple programming paradigms,
including structured, object-oriented and functional programming. Python is often described
as a batteries included language due to its comprehensive standard library.

Guido van Rossum began working on Python in the late 1980s as a successor to the ABC
programming language and first released it in 1991 as Python 0.9.0. Python 2.0 was released
in 2000. Python 3.0, released in 2008, was a major revision not completely
backward-compatible with earlier versions. Python 2.7.18, released in 2020, was the last
release of Python 2. Python consistently ranks as one of the most popular programming
languages, and has gained widespread use in the machine learning community.

Python interpreters are available for many operating systems. CPython, the reference
implementation, is developed under a community-driven model. The language provides built-in
types such as lists, dictionaries, sets and tuples. List comprehensions, decorators and
generators are idiomatic features. The standard library includes modules for regular
expressions, networking, file handling and unit testing. Third-party packages are installed
with pip, the package installer for Python.

Python is widely used in web development with frameworks such as Django and FastAPI, in data
science with libraries such as pandas and NumPy, and in machine learning with PyTorch and
scikit-learn. Automated testing with pytest and type checking with mypy are common practices
in professional Python codebases. Asynchronous programming is supported through the asyncio
module, which powers async web frameworks and I/O-bound applications.

The Python community organizes conferences such as PyCon and promotes coding standards
through PEP 8. The language continues to evolve under the stewardship of the Python Software
Foundation. New releases follow a yearly cadence, with performance improvements and new
syntax features in each major version. Developers value Python for its gentle learning
curve, expressive syntax and vast ecosystem of open source packages.
"""

RECIPE_TEXT = """Mantı, Orta Asya kökenli ve Türk mutfağının en sevilen yemeklerinden
biridir. Geleneksel tarifte önce hamur hazırlanır: un, yumurta, su ve bir tutam tuz yoğrularak
kulak memesi kıvamında bir hamur elde edilir. Hamur dinlendirilirken iç harcı hazırlanır.
Kıyma, ince kıyılmış soğan, tuz, karabiber ve pul biber bir kasede karıştırılır.

Dinlenen hamur ince bir şekilde açılır ve küçük kareler halinde kesilir. Her karenin ortasına
bir çay kaşığı kadar iç harç konur. Karelerin uçları birleştirilerek bohça şeklinde kapatılır.
Hazırlanan mantılar unlanmış bir tepsiye dizilir. Bol tuzlu su kaynatılır ve mantılar kaynayan
suya atılarak yaklaşık on dakika haşlanır.

Servis için sarımsaklı yoğurt hazırlanır. Haşlanan mantılar süzülerek tabaklara alınır,
üzerine sarımsaklı yoğurt dökülür. Son olarak tereyağında kızdırılmış salça, nane ve pul biber
sosu gezdirilir. İsteğe göre üzerine kuru nane serpilir. Mantı sıcak servis edilir.

Mantının Kayseri, Sinop ve Çorum gibi birçok yörede farklı çeşitleri yapılır. Kimi yörelerde
mantı fırında, kimi yörelerde ise suda haşlanarak pişirilir. Yanında genellikle ayran veya
turşu ikram edilir. Mantı yapımı emek isteyen bir süreçtir; bu yüzden geleneksel olarak
kalabalık aileler birlikte oturup mantı açarlar. Türk kültüründe mantı sofrası, bir araya
gelmenin ve paylaşmanın sembolü olarak görülür.
"""


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


def test_search_empty_query(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Boş query → 422 (validation)."""
    resp = app_client.post(SEARCH_URL, json={"query": ""}, headers=auth_headers)
    assert resp.status_code == 422


def test_search_no_documents(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Hiç doküman yokken arama boş döner."""
    resp = app_client.post(SEARCH_URL, json={"query": "herhangi bir şey"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_returns_relevant_chunks(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Python query'si Python dokümanını ilk sırada getirir; similarity 0-1 float."""
    python_doc = _create_and_index(app_client, auth_headers, "Python Programlama", PYTHON_TEXT)
    _create_and_index(app_client, auth_headers, "Mantı Tarifi", RECIPE_TEXT)
    resp = app_client.post(SEARCH_URL, json={"query": "Python"}, headers=auth_headers)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert results[0]["document_id"] == python_doc["id"]
    for item in results:
        assert isinstance(item["similarity"], float)
        assert 0.0 <= item["similarity"] <= 1.0


def test_search_with_document_filter(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """document_ids filtresi Python dokümanına daraltılınca 'yemek' boş döner."""
    python_doc = _create_and_index(app_client, auth_headers, "Python Programlama", PYTHON_TEXT)
    _create_and_index(app_client, auth_headers, "Mantı Tarifi", RECIPE_TEXT)
    resp = app_client.post(
        SEARCH_URL,
        json={"query": "yemek", "document_ids": [python_doc["id"]]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_search_other_users_chunks(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """bob, alice'in index'lediği chunk'ları arayamaz (owner filtresi)."""
    _create_and_index(app_client, auth_headers, "Python Programlama", PYTHON_TEXT)
    bob_headers = _headers_for(app_client, "bob")
    resp = app_client.post(SEARCH_URL, json={"query": "Python"}, headers=bob_headers)
    assert resp.status_code == 200
    assert resp.json()["results"] == []
