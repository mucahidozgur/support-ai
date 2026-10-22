"""Doküman CRUD servisi."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate


class DocumentService:
    """Sahip (owner_id) kapsamında doküman CRUD işlemleri."""

    def __init__(self, db: AsyncSession, owner_id: UUID) -> None:
        self.db = db
        self.owner_id = owner_id

    async def create(self, data: DocumentCreate) -> Document:
        """Yeni doküman oluşturur."""
        doc = Document(**data.model_dump(), owner_id=self.owner_id)
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def list(self, limit: int = 20, offset: int = 0) -> tuple[list[Document], int]:
        """Kullanıcının dokümanlarını en yeni önce olacak şekilde listeler."""
        limit = min(limit, 100)  # üst sınır
        where = Document.owner_id == self.owner_id
        total = await self.db.scalar(select(func.count()).select_from(Document).where(where))
        stmt = (
            select(Document)
            .where(where)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        docs = list((await self.db.scalars(stmt)).all())
        return docs, int(total or 0)

    async def get(self, document_id: UUID) -> Document | None:
        """Dokümanı owner filtresiyle getirir; bulunamazsa None."""
        stmt = select(Document).where(
            Document.id == document_id, Document.owner_id == self.owner_id
        )
        return await self.db.scalar(stmt)

    async def update(self, document_id: UUID, data: DocumentUpdate) -> Document | None:
        """Yalnızca set edilmiş alanları günceller; yoksa None."""
        doc = await self.get(document_id)
        if doc is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(doc, field, value)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def delete(self, document_id: UUID) -> bool:
        """Dokümanı siler (chunk'lar cascade ile silinir); yoksa False."""
        doc = await self.get(document_id)
        if doc is None:
            return False
        await self.db.delete(doc)
        await self.db.commit()
        return True
