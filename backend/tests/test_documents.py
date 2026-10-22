"""Document CRUD endpoint testleri."""

from uuid import uuid4

from fastapi.testclient import TestClient

DOCS_URL = "/api/documents"


def _headers_for(app_client: TestClient, username: str) -> dict[str, str]:
    """Verilen username için login olup Bearer header döndürür."""
    resp = app_client.post("/api/auth/login", json={"username": username, "password": "x"})
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create(app_client: TestClient, headers: dict[str, str], title: str) -> dict:
    """Yardımcı: doküman oluşturur ve JSON body döndürür."""
    resp = app_client.post(
        DOCS_URL, json={"title": title, "content": f"content of {title}"}, headers=headers
    )
    assert resp.status_code == 201
    return resp.json()


def test_create_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST ile doküman oluşturur; id, title, owner_id döner."""
    resp = app_client.post(
        DOCS_URL,
        json={"title": "Toplantı notları", "content": "Önemli içerik"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["title"] == "Toplantı notları"
    assert body["owner_id"]


def test_create_document_requires_auth(app_client: TestClient) -> None:
    """Token'sız POST reddedilir."""
    resp = app_client.post(DOCS_URL, json={"title": "x", "content": "y"})
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401


def test_list_documents_empty(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Hiç dokümanı olmayan kullanıcı boş liste alır."""
    resp = app_client.get(DOCS_URL, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_documents(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """3 doküman en yeniden eskiye (DESC) listelenir."""
    for title in ("doc1", "doc2", "doc3"):
        _create(app_client, auth_headers, title)
    resp = app_client.get(DOCS_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [item["title"] for item in body["items"]] == ["doc3", "doc2", "doc1"]


def test_list_documents_pagination(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """limit=2 offset=0 → 2 item döner, total 5 kalır."""
    for i in range(5):
        _create(app_client, auth_headers, f"doc{i}")
    resp = app_client.get(DOCS_URL, params={"limit": 2, "offset": 0}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2


def test_get_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Oluşturulan doküman id ile getirilir."""
    created = _create(app_client, auth_headers, "Sözleşme")
    resp = app_client.get(f"{DOCS_URL}/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Sözleşme"


def test_get_document_not_found(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Var olmayan id → 404."""
    resp = app_client.get(f"{DOCS_URL}/{uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Document not found"


def test_get_other_users_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """bob, alice'in dokümanını göremez (404 — bilgi sızdırma yok)."""
    created = _create(app_client, auth_headers, "alice gizli")
    bob_headers = _headers_for(app_client, "bob")
    resp = app_client.get(f"{DOCS_URL}/{created['id']}", headers=bob_headers)
    assert resp.status_code == 404


def test_update_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """PUT ile title+content güncellenir, updated_at dolar."""
    created = _create(app_client, auth_headers, "eski başlık")
    resp = app_client.put(
        f"{DOCS_URL}/{created['id']}",
        json={"title": "yeni başlık", "content": "yeni içerik"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "yeni başlık"
    assert body["content"] == "yeni içerik"
    assert body["updated_at"] is not None
    assert body["updated_at"] != created["created_at"]


def test_update_other_users_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """bob, alice'in dokümanını güncelleyemez → 404."""
    created = _create(app_client, auth_headers, "alice dokümanı")
    bob_headers = _headers_for(app_client, "bob")
    resp = app_client.put(
        f"{DOCS_URL}/{created['id']}",
        json={"title": "hack"},
        headers=bob_headers,
    )
    assert resp.status_code == 404


def test_delete_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """DELETE → 204; sonraki GET → 404."""
    created = _create(app_client, auth_headers, "silinecek")
    resp = app_client.delete(f"{DOCS_URL}/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    resp = app_client.get(f"{DOCS_URL}/{created['id']}", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_other_users_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """bob, alice'in dokümanını silemez → 404."""
    created = _create(app_client, auth_headers, "alice dokümanı")
    bob_headers = _headers_for(app_client, "bob")
    resp = app_client.delete(f"{DOCS_URL}/{created['id']}", headers=bob_headers)
    assert resp.status_code == 404
