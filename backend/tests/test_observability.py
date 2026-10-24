"""Langfuse observability testleri (anahtarsız no-op + feedback endpoint)."""

import pytest
from fastapi.testclient import TestClient

from app.core import observability

FEEDBACK_URL = "/api/ai/feedback"


def test_langfuse_disabled_when_no_keys() -> None:
    """Anahtarlar boşsa callback/client None döner; uygulama çalışmaya devam eder.

    .env dosyasında LANGFUSE anahtarları dolu DEĞİL — bu test gerçek konfigürasyonu
    doğrular (lru_cache temizlenerek deterministik çalışır).
    """
    observability.is_langfuse_enabled.cache_clear()
    assert observability.is_langfuse_enabled() is False
    assert observability.get_langfuse_callback() is None
    assert observability.get_langfuse_client() is None
    assert observability.callback_config() == {}

    # observe_rag passthrough olmalı: fonksiyon aynen döner.
    def sample() -> str:
        return "x"

    assert observability.observe_rag("sample")(sample) is sample


def test_feedback_endpoint_auth_required(app_client: TestClient) -> None:
    """Token'sız feedback isteği reddedilir."""
    resp = app_client.post(FEEDBACK_URL, json={"trace_id": "t1", "score": 1})
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401


def test_feedback_endpoint_valid_payload(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Geçerli payload ile skor Langfuse'a gönderilir (mock client)."""
    scores: list = []

    class _FakeClient:
        def create_score(self, **kwargs) -> None:
            scores.append(kwargs)

    monkeypatch.setattr("app.api.ai.get_langfuse_client", lambda: _FakeClient())
    resp = app_client.post(
        FEEDBACK_URL,
        json={"trace_id": "trace-123", "score": 1, "comment": "çok iyi"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert scores == [
        {
            "name": "user_feedback",
            "value": 1.0,
            "trace_id": "trace-123",
            "comment": "çok iyi",
        }
    ]


def test_feedback_endpoint_disabled(
    app_client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Observability devre dışıysa 503 döner (uygulama çökmez)."""
    monkeypatch.setattr("app.api.ai.get_langfuse_client", lambda: None)
    resp = app_client.post(FEEDBACK_URL, json={"trace_id": "t1", "score": 0}, headers=auth_headers)
    assert resp.status_code == 503


def test_feedback_endpoint_invalid_score(
    app_client: TestClient, auth_headers: dict[str, str]
) -> None:
    """score 0/1 dışındaysa 422 (validation)."""
    resp = app_client.post(FEEDBACK_URL, json={"trace_id": "t1", "score": 5}, headers=auth_headers)
    assert resp.status_code == 422
