"""Auth endpoint testleri."""

from fastapi.testclient import TestClient

from app.core.security import decode_token


def test_login_success(app_client: TestClient) -> None:
    """Geçerli login isteği 200 ve token döndürür."""
    resp = app_client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_same_username_same_user_id(app_client: TestClient) -> None:
    """Aynı username için üretilen token'ların sub değeri aynı olmalı."""
    login = {"username": "alice", "password": "x"}
    token1: str = app_client.post("/api/auth/login", json=login).json()["access_token"]
    token2: str = app_client.post("/api/auth/login", json=login).json()["access_token"]
    assert decode_token(token1)["sub"] == decode_token(token2)["sub"]


def test_me_without_token(app_client: TestClient) -> None:
    """Token'sız istek reddedilir (HTTPBearer: 403)."""
    resp = app_client.get("/api/auth/me")
    assert resp.status_code in (401, 403)


def test_me_with_valid_token(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Geçerli token ile /me kullanıcı bilgisini döndürür."""
    resp = app_client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_me_with_invalid_token(app_client: TestClient) -> None:
    """Geçersiz token 401 döndürür."""
    resp = app_client.get("/api/auth/me", headers={"Authorization": "Bearer invalidtoken"})
    assert resp.status_code == 401
