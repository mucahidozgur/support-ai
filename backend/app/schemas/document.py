"""Doküman ile ilgili Pydantic modelleri."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    """Yeni doküman girdisi."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source: str = Field(default="upload", max_length=100)


class DocumentUpdate(BaseModel):
    """Güncellenebilir alanlar; source güncellenemez."""

    title: str | None = None
    content: str | None = None


class DocumentRead(BaseModel):
    """Dokümanın tam gösterimi."""

    id: UUID
    title: str
    content: str
    owner_id: UUID
    source: str
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class DocumentListItem(BaseModel):
    """Liste görünümü: içerik yerine kısa önizleme."""

    id: UUID
    title: str
    source: str
    created_at: datetime
    content_preview: str  # ilk 200 karakter

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Sayfalanmış liste yanıtı."""

    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int
