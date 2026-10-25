"""Analitik yanıt şemaları."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AnalyticsStats(BaseModel):
    """Panodaki KPI kartlarının verileri."""

    total_queries: int
    avg_faithfulness: float
    insufficient_context_rate: float
    avg_latency_ms: float
    feedback_positive: int
    feedback_negative: int


class RecentQueryItem(BaseModel):
    """Son sorgu logu kaydı."""

    model_config = ConfigDict(from_attributes=True)  # SQLAlchemy modelinden doğrudan

    id: UUID
    query: str
    faithfulness: float | None
    feedback: int | None
    had_context: bool
    latency_ms: int | None
    created_at: datetime


class TopQueryItem(BaseModel):
    """En çok sorulan sorgu."""

    query: str
    count: int
