"""Analitik endpoint testleri (query_logs üzerinden)."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query_log import QueryLog

STATS_URL = "/api/analytics/stats"
RECENT_URL = "/api/analytics/recent-queries"
TOP_URL = "/api/analytics/top-queries"
CHAT_URL = "/api/ai/chat"


async def _insert_log(
    db_session: AsyncSession,
    query: str,
    *,
    faithfulness: float | None = None,
    had_context: bool = True,
    latency_ms: int | None = None,
    feedback: int | None = None,
) -> None:
    """Test verisi: doğrudan query_logs'a satır ekler."""
    db_session.add(
        QueryLog(
            query=query,
            faithfulness=faithfulness,
            had_context=had_context,
            latency_ms=latency_ms,
            feedback=feedback,
        )
    )
    await db_session.commit()


async def _log_count(db_session: AsyncSession) -> int:
    """query_logs'taki satır sayısını döndürür."""
    return (await db_session.scalar(select(func.count()).select_from(QueryLog))) or 0


def test_stats_empty_db(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Boş DB'de tüm KPI'lar sıfır döner."""
    resp = app_client.get(STATS_URL, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "total_queries": 0,
        "avg_faithfulness": 0.0,
        "insufficient_context_rate": 0.0,
        "avg_latency_ms": 0.0,
        "feedback_positive": 0,
        "feedback_negative": 0,
    }


async def test_stats_with_data(
    app_client: TestClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Birkaç log eklenince ortalamalar doğru hesaplanır."""
    await _insert_log(
        db_session, "q1", faithfulness=0.9, had_context=True, latency_ms=100, feedback=1
    )
    await _insert_log(
        db_session, "q2", faithfulness=0.5, had_context=False, latency_ms=200, feedback=0
    )
    await _insert_log(db_session, "q3", faithfulness=None, had_context=True, latency_ms=300)
    await _insert_log(
        db_session, "q4", faithfulness=0.8, had_context=True, latency_ms=400, feedback=1
    )

    resp = app_client.get(STATS_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_queries"] == 4
    assert body["avg_faithfulness"] == round((0.9 + 0.5 + 0.8) / 3, 3)  # 0.733
    assert body["insufficient_context_rate"] == 0.25
    assert body["avg_latency_ms"] == 250.0
    assert body["feedback_positive"] == 2
    assert body["feedback_negative"] == 1


async def test_recent_queries_limit(
    app_client: TestClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Limit parametresi doğru uygulanır."""
    for i in range(25):
        await _insert_log(db_session, f"soru-{i}")

    resp = app_client.get(RECENT_URL, headers=auth_headers)  # varsayılan 20
    assert resp.status_code == 200
    assert len(resp.json()) == 20

    resp5 = app_client.get(RECENT_URL, params={"limit": 5}, headers=auth_headers)
    assert len(resp5.json()) == 5
    item = resp5.json()[0]
    assert set(item) == {
        "id",
        "query",
        "faithfulness",
        "feedback",
        "had_context",
        "latency_ms",
        "created_at",
    }

    assert await _log_count(db_session) == 25  # endpoint veriyi silmez


async def test_top_queries(
    app_client: TestClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """En çok sorulan sorgular sayılarıyla döner."""
    for _ in range(3):
        await _insert_log(db_session, "popüler soru")
    await _insert_log(db_session, "nadir soru")

    resp = app_client.get(TOP_URL, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body[0] == {"query": "popüler soru", "count": 3}
    assert {"query": "nadir soru", "count": 1} in body


async def test_query_log_written_on_chat(
    app_client: TestClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Chat isteği (yetersiz context) query_logs'a yazılır; log_id done event'inde."""
    with app_client.stream(
        "POST", CHAT_URL, json={"query": "log testi sorusu?"}, headers=auth_headers
    ) as resp:
        assert resp.status_code == 200
        raw = resp.read().decode("utf-8")
    assert "insufficient_context" in raw
    assert "log_id" in raw

    rows = (await db_session.execute(select(QueryLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.query == "log testi sorusu?"
    assert row.had_context is False
    assert row.latency_ms is not None


def test_analytics_requires_auth(app_client: TestClient) -> None:
    """Token'sız analitik istekleri reddedilir."""
    assert app_client.get(STATS_URL).status_code in (401, 403)
    assert app_client.get(RECENT_URL).status_code in (401, 403)
    assert app_client.get(TOP_URL).status_code in (401, 403)
