"""Uygulama ayarları: .env dosyasından okunur."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Support AI yapılandırma değerleri."""

    DATABASE_URL: str = "postgresql+asyncpg://support:support@localhost:5434/support"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "qwen/qwen3.8-27b"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    JWT_SECRET: str = "changeme"
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MIN: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3002"]
    TEST_DATABASE_URL: str | None = None  # host'tan test DB'si (localhost)
    TEST_DATABASE_URL_DOCKER: str | None = None  # container içinden test DB'si (postgres)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Ayarları cache'leyerek döndürür (process başına tek instance)."""
    return Settings()
