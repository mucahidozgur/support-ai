"""Sorgu logu modeli: analitik panosu için chat metrikleri."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QueryLog(Base):
    """Her chat isteğinin metriklerini tutar (feedback sonradan güncellenir)."""

    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(Text)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    had_context: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 = up, 0 = down
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
