"""Sağlık kontrolü endpoint testi."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    """GET /health 200 ve beklenen gövdeyi dönmeli."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "support-ai"}
