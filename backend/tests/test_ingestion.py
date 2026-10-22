"""Ingestion endpoint testleri."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk

DOCS_URL = "/api/documents"

LONG_TEXT = """PostgreSQL is a powerful, open source object-relational database system with over
35 years of active development that has earned it a strong reputation for reliability, feature
robustness, and performance. PostgreSQL runs on all major operating systems and has been
ACID-compliant since 2001. It has powerful add-ons such as the popular PostGIS geospatial
database extender. The database supports both SQL for relational queries and JSON for
non-relational queries.

PostgreSQL features include user-defined types, table inheritance, sophisticated locking
mechanisms, foreign key referential integrity, views, rules, subquery, and nested
transactions. It supports multi-version concurrency control, which allows readers and
writers to work without blocking each other. The system is highly extensible: users can add
new data types, functions, operators, aggregate functions, index methods and procedural
languages. Extensions such as pgvector bring vector similarity search to PostgreSQL, making
it a popular choice for AI applications that need to store embeddings alongside relational
data.

The query planner in PostgreSQL is sophisticated, using cost-based optimization with
statistics collected by the ANALYZE command. Index types include B-tree, hash, GiST, SP-GiST,
GIN and BRIN. Full-text search is built in, with support for ranking and phrase search.
Streaming replication and logical replication allow building highly available clusters.
Point-in-time recovery is possible with continuous archiving and write-ahead logging, which
records every change before it is applied to the data files.

PostgreSQL is released under the PostgreSQL License, a liberal open source license similar to
the BSD or MIT licenses. The project is developed by a worldwide community of contributors.
Major versions are released approximately once per year, and each version receives five years
of updates. Tools such as pg_dump and pg_restore simplify backup and migration. The pg_stat
views expose runtime statistics, and the EXPLAIN command shows how queries are executed,
which makes performance tuning an empirical and approachable task.
"""


def _headers_for(app_client: TestClient, username: str) -> dict[str, str]:
    """Verilen username için login olup Bearer header döndürür."""
    resp = app_client.post("/api/auth/login", json={"username": username, "password": "x"})
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create(app_client: TestClient, headers: dict[str, str], title: str, content: str) -> dict:
    """Yardımcı: doküman oluşturur ve JSON body döndürür."""
    resp = app_client.post(DOCS_URL, json={"title": title, "content": content}, headers=headers)
    assert resp.status_code == 201
    return resp.json()


def test_index_empty_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """Yalnızca whitespace içeren doküman → chunks_created=0."""
    created = _create(app_client, auth_headers, "boş doküman", "   ")
    resp = app_client.post(f"{DOCS_URL}/{created['id']}/index", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks_created"] == 0
    assert body["chunks_deleted"] == 0


async def test_index_creates_chunks(
    app_client: TestClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Uzun metin index'lenince >=2 chunk oluşur ve DB'ye yazılır."""
    created = _create(app_client, auth_headers, "PostgreSQL Rehberi", LONG_TEXT)
    resp = app_client.post(f"{DOCS_URL}/{created['id']}/index", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunks_created"] >= 2
    count = await db_session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == UUID(created["id"]))
    )
    assert count == body["chunks_created"]


def test_index_is_idempotent(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """İkinci index'leme eskileri siler ve aynı sayıda chunk üretir."""
    created = _create(app_client, auth_headers, "idempotent test", LONG_TEXT)
    first = app_client.post(f"{DOCS_URL}/{created['id']}/index", headers=auth_headers).json()
    second = app_client.post(f"{DOCS_URL}/{created['id']}/index", headers=auth_headers).json()
    assert first["chunks_created"] > 0
    assert second["chunks_deleted"] == first["chunks_created"]
    assert second["chunks_created"] == first["chunks_created"]


def test_index_other_users_document(app_client: TestClient, auth_headers: dict[str, str]) -> None:
    """bob, alice'in dokümanını index'leyemez → 404."""
    created = _create(app_client, auth_headers, "alice dokümanı", LONG_TEXT)
    bob_headers = _headers_for(app_client, "bob")
    resp = app_client.post(f"{DOCS_URL}/{created['id']}/index", headers=bob_headers)
    assert resp.status_code == 404


def test_index_requires_auth(app_client: TestClient) -> None:
    """Token'sız index isteği reddedilir."""
    resp = app_client.post(f"{DOCS_URL}/{uuid4()}/index")
    assert resp.status_code in (401, 403)  # HTTPBearer: eski FastAPI 403, yeni 401
