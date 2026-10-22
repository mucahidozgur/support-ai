"""FastAPI uygulama giriş noktası."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.core.config import get_settings
from app.core.db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Uygulama ayağa kalkarken DB altyapısını hazırlar."""
    await init_db()
    yield


app = FastAPI(title="Support AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(ai_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Sağlık kontrolü."""
    return {"status": "ok", "service": "support-ai"}
