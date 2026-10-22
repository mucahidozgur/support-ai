"""LLM ve embedding soyutlama katmanı."""

from functools import lru_cache

from langchain_openai import ChatOpenAI
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_llm() -> ChatOpenAI:
    """Groq üzerindeki chat modelini cache'leyerek döndürür."""
    return ChatOpenAI(
        base_url=settings.GROQ_BASE_URL,
        api_key=settings.GROQ_API_KEY,
        model=settings.LLM_MODEL,
        temperature=0,
        streaming=True,
    )


class LocalEmbeddings:
    """Yerel sentence-transformers modeliyle embedding üretir."""

    @property
    @lru_cache  # noqa: B019 (spec: property üzerinde lru_cache; tek instance üzerinden çağrılır)
    def _model(self) -> SentenceTransformer:
        """Modeli bir kez yükler ve cache'ler."""
        return SentenceTransformer(settings.EMBEDDING_MODEL)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Doküman listesini normalize embedding vektörlerine çevirir."""
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        """Tek bir sorgu metnini embedding vektörüne çevirir."""
        return self.embed_documents([text])[0]


@lru_cache
def get_embeddings() -> LocalEmbeddings:
    """Uygulama genelinde tek embedding instance'ı döndürür."""
    return LocalEmbeddings()
