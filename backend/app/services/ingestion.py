"""Doküman indexing servisi: chunk + embed + chunks tablosuna yazma."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_embeddings
from app.models.document import Chunk, Document
from app.services.chunking import chunk_text


class DocumentIngestionService:
    """Dokümanı chunk'layıp embedding'lerini chunks tablosuna yazar."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id
        self.embeddings = get_embeddings()

    async def index_document(self, document_id: UUID) -> dict | None:
        """Dokümanı index'ler; varsa eski chunk'ları siler. Doküman yoksa None."""
        doc = await self._get_owned_document(document_id)
        if doc is None:
            return None

        result = await self.db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        chunks_deleted = result.rowcount or 0

        chunks = chunk_text(doc.content)
        if chunks:
            embeddings = self.embeddings.embed_documents(chunks)
            self.db.add_all(
                [
                    Chunk(
                        document_id=document_id,
                        content=content,
                        embedding=embedding,
                        chunk_index=idx,
                    )
                    for idx, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
                ]
            )

        await self.db.commit()
        return {
            "document_id": document_id,
            "chunks_created": len(chunks),
            "chunks_deleted": chunks_deleted,
        }

    async def _get_owned_document(self, document_id: UUID) -> Document | None:
        """Dokümanı owner filtresiyle getirir."""
        stmt = select(Document).where(
            Document.id == document_id, Document.owner_id == self.owner_id
        )
        return await self.db.scalar(stmt)
