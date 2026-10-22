"""Ortak test fixture'ları (testler ayrı test DB'sine bağlanır; prod DB'ye dokunmaz)."""

import asyncio
import os
import warnings
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

# Embedding modeli host'ta cache'li; huggingface_hub'ın model yüklemesindeki etag
# doğrulama ağ çağrısını kapat. Flaky ağda bu çağrı WinError 10054 (bağlantı
# reset) üretip testleri rastgele düşürüyordu. app import'undan ÖNCE olmalı.
os.environ["HF_HUB_OFFLINE"] = "1"

# Host pytest'i backend/ altından koşar; repo kökündeki .env'i elle yükle
# (docker compose env_file'ı container'a enjekte eder, host bunu görmez).
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()
TEST_DATABASE_URL = _settings.TEST_DATABASE_URL
if TEST_DATABASE_URL:
    # Uygulamanın DATABASE_URL'ini test DB'sine yönlendir; böylece testler
    # container'ın kullandığı prod DB'sine hiç dokunmaz. db.py engine'i modül
    # import'unda kurduğu için bu atama app import'undan ÖNCE yapılmalı.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    get_settings.cache_clear()

from app.core.db import Base
from app.main import app


@pytest.fixture(scope="session")
def app_client() -> TestClient:
    """Lifespan dahil uygulama test client'ı (test DB'sine bağlanır)."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_db(app_client: TestClient) -> Iterator[None]:
    """Test DB'sinde extension + tabloları hazırlar (idempotent)."""
    if not TEST_DATABASE_URL:
        yield
        return

    async def _prepare() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    app_client.portal.call(_prepare)
    yield


@pytest.fixture(scope="session", autouse=True)
def _dispose_app_engine(app_client: TestClient) -> Iterator[None]:
    """Session sonunda app engine'ini portal loop'u üzerinde dispose eder.

    asyncpg bağlantıları oluşturuldukları event loop'a sabitlidir. İstekler
    TestClient portal'ının loop'unda koştuğu için pool bağlantıları orada
    oluşur; portal kapanmadan engine'i KENDİ loop'unda kapatmazsak GC, kapalı
    loop üzerindeki bağlantıları temizlemeye çalışırken takılıyordu
    (teardown hang'i / "greenlet is being finalized" hatası).
    """
    yield
    from app.core.db import engine

    app_client.portal.call(engine.dispose)


@pytest.fixture
def auth_headers(app_client: TestClient) -> dict[str, str]:
    """alice için login olup Bearer header döndürür."""
    resp = app_client.post("/api/auth/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Taze engine'li async DB oturumu (test DB'sine; test içi doğrulamalar için)."""
    engine = create_async_engine(get_settings().DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture
def db_cleanup() -> Iterator[None]:
    """Her test öncesi/sonrası TEST DB'sindeki documents tablosunu temizler.

    Guard: TEST_DATABASE_URL set değilse prod DB'ye dokunmayı reddeder,
    uyarı basar ve temizliği atlar.

    Not: asyncio.run() yeni bir event loop açar; asyncpg bağlantıları loop'a
    sabitlendiği için modül engine'ini burada KULLANMAYIZ — her temizlik kendi
    loop'u içinde taze bir engine oluşturur ve kapatır.
    """
    if not TEST_DATABASE_URL:
        warnings.warn(
            "TEST_DATABASE_URL set değil; test temizliği atlanıyor — prod DB'ye dokunulmaz!",
            UserWarning,
            stacklevel=2,
        )
        yield
        return

    async def _clean() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DELETE FROM documents"))
        finally:
            await engine.dispose()

    asyncio.run(_clean())
    yield
    asyncio.run(_clean())


@pytest.fixture(autouse=True)
def clean_documents(db_cleanup: None) -> Iterator[None]:
    """Her testten önce/sonra test DB'sini temizler (chunks CASCADE ile gider)."""
    yield
