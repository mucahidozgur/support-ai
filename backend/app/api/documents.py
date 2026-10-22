"""Document CRUD endpoint'leri."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.document import Document
from app.schemas.ai import IndexResponse
from app.schemas.auth import UserInfo
from app.schemas.document import (
    DocumentCreate,
    DocumentListItem,
    DocumentListResponse,
    DocumentRead,
    DocumentUpdate,
)
from app.services.document import DocumentService
from app.services.ingestion import DocumentIngestionService

router = APIRouter(prefix="/api/documents", tags=["documents"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[UserInfo, Depends(get_current_user)]


@router.post("", response_model=DocumentRead, status_code=201)
async def create_document(body: DocumentCreate, db: DbDep, current_user: UserDep) -> Document:
    """Yeni doküman oluşturur."""
    service = DocumentService(db, UUID(current_user.id))
    return await service.create(body)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    db: DbDep,
    current_user: UserDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    """Kullanıcının dokümanlarını sayfalar halinde listeler."""
    service = DocumentService(db, UUID(current_user.id))
    docs, total = await service.list(limit, offset)
    items = [
        DocumentListItem(
            id=doc.id,
            title=doc.title,
            source=doc.source,
            created_at=doc.created_at,
            content_preview=doc.content[:200],
        )
        for doc in docs
    ]
    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{document_id}/index", response_model=IndexResponse)
async def index_document(document_id: UUID, db: DbDep, current_user: UserDep) -> IndexResponse:
    """Dokümanı chunk'layıp embedding'lerini index'ler."""
    result = await DocumentIngestionService(db, UUID(current_user.id)).index_document(document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return IndexResponse(**result)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, db: DbDep, current_user: UserDep) -> Document:
    """Tek dokümanı döndürür; yoksa 404."""
    doc = await DocumentService(db, UUID(current_user.id)).get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.put("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: UUID, body: DocumentUpdate, db: DbDep, current_user: UserDep
) -> Document:
    """Dokümanı günceller; yoksa 404."""
    doc = await DocumentService(db, UUID(current_user.id)).update(document_id, body)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, db: DbDep, current_user: UserDep) -> None:
    """Dokümanı siler; yoksa 404."""
    deleted = await DocumentService(db, UUID(current_user.id)).delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
