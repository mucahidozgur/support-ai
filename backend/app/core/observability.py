"""Langfuse observability katmanı.

Kurumsal RAG sistemi kara kutu olamaz: her retrieval, rerank ve doğrulama
adımı trace edilmelidir. Ancak observability ASLA akışı bozmaz:

- Anahtarlar (.env) boşsa her şey no-op'tur (None callback, passthrough dekoratör).
- Langfuse çağrıları try/except ile korunur; yalnızca logger.warning basılır.
"""

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@lru_cache
def is_langfuse_enabled() -> bool:
    """Langfuse anahtarları doluysa True döner (cache'li)."""
    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def get_langfuse_client():
    """Langfuse client'ı; devre dışıysa veya kurulum hatasıysa None."""
    if not is_langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
    except Exception:
        logger.warning("Langfuse client kurulamadı; observability devre dışı.", exc_info=True)
        return None


def get_langfuse_callback():
    """LangChain CallbackHandler; devre dışıysa veya hata olursa None."""
    if not is_langfuse_enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.warning("Langfuse callback kurulamadı; trace'ler atlanıyor.", exc_info=True)
        return None


def callback_config() -> dict[str, Any]:
    """LangChain/LangGraph çağrıları için config parçası; devre dışıysa boş."""
    handler = get_langfuse_callback()
    if handler is None:
        return {}
    return {"callbacks": [handler]}


def observe_rag(name: str) -> Callable[[Callable], Callable]:
    """RAG adımını izleyen dekoratör; devre dışıysa birebir passthrough.

    @observe dekoratörünü gerçekten uygulamak yalnızca Langfuse aktifken yapılır;
    böylece anahtarsız ortamda span üretimi dahil hiçbir yan etki oluşmaz.
    """
    if not is_langfuse_enabled():
        return lambda func: func
    try:
        from langfuse import observe

        return observe(name=name)
    except Exception:  # noqa: BLE001 (spec: observability hatası asla akışı bozmaz)
        logger.warning("Langfuse @observe uygulanamadı (%s); izleme atlandı.", name)
        return lambda func: func


def update_observation_input(data: dict[str, Any]) -> None:
    """Aktif span'e input metadata'sı yazar; devre dışıysa sessiz geçer."""
    if not is_langfuse_enabled():
        return
    try:
        client = get_langfuse_client()
        if client is not None:
            client.update_current_span(input=data)
    except Exception as exc:  # noqa: BLE001 (spec: observability hatası asla akışı bozmaz)
        logger.warning("Langfuse input metadata yazılamadı: %s", exc)


def update_observation_output(data: dict[str, Any]) -> None:
    """Aktif span'e output metadata'sı yazar; devre dışıysa sessiz geçer."""
    if not is_langfuse_enabled():
        return
    try:
        client = get_langfuse_client()
        if client is not None:
            client.update_current_span(output=data)
    except Exception as exc:  # noqa: BLE001 (spec: observability hatası asla akışı bozmaz)
        logger.warning("Langfuse output metadata yazılamadı: %s", exc)
