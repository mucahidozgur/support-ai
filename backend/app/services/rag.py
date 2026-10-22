"""RAG arama servisi (pgvector cosine similarity)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_embeddings
from app.models.document import Chunk, Document

# Bu eşiğin altındaki benzerlikler ilgisiz kabul edilir. Faz 3a'da gerçek modelle
# ölçülerek belirlendi: ilgili sorgu 0.68-0.82, ilgisiz sorgu 0.40-0.47 üretti.
MIN_SIMILARITY = 0.55


class RAGService:
    """Query embedding'i ile pgvector üzerinde benzerlik araması."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.embeddings = get_embeddings()

    async def search(
        self,
        query: str,
        document_ids: list[UUID] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """En benzer chunk'ları döndürür; owner filtresi JOIN ile uygulanır."""
        query_emb = self.embeddings.embed_query(query)
        similarity = (1 - Chunk.embedding.cosine_distance(query_emb)).label("similarity")
        stmt = (
            select(Chunk, Document.title, similarity)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(similarity >= MIN_SIMILARITY)
            .order_by(similarity.desc())
            .limit(limit)
        )
        if document_ids is not None:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))

        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": float(sim),
                "chunk_index": chunk.chunk_index,
            }
            for chunk, title, sim in rows
        ]

    async def get_all_chunks(self, document_id: UUID) -> list[dict]:
        """Belirtilen dokümanın TÜM chunk'larını döner (chunk_index sıralı).

        Owner filtresi uygulanır. similarity alanı 1.0 ile doldurulur —
        burada semantik skor yok, chunk'lar dokümanın kendisi.
        """
        stmt = (
            select(Chunk, Document.title)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.owner_id == self.owner_id)
            .where(Document.id == document_id)
            .order_by(Chunk.chunk_index)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": title,
                "content": chunk.content,
                "similarity": 1.0,
                "chunk_index": chunk.chunk_index,
            }
            for chunk, title in rows
        ]
