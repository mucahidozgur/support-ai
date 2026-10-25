"""Analitik endpoint'leri: KPI'lar, son sorgular, popüler sorgular."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.query_log import QueryLog
from app.schemas.analytics import AnalyticsStats, RecentQueryItem, TopQueryItem
from app.schemas.auth import UserInfo

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[UserInfo, Depends(get_current_user)]


@router.get("/stats", response_model=AnalyticsStats)
async def stats(db: DbDep, current_user: UserDep) -> AnalyticsStats:
    """KPI özeti: sorgu sayısı, ortalama faithfulness, yetersiz context oranı,
    ortalama gecikme ve feedback dağılımı."""
    total = await db.scalar(select(func.count()).select_from(QueryLog)) or 0
    avg_faith = await db.scalar(select(func.avg(QueryLog.faithfulness))) or 0.0
    no_context = (
        await db.scalar(
            select(func.count()).select_from(QueryLog).where(QueryLog.had_context.is_(False))
        )
        or 0
    )
    avg_latency = await db.scalar(select(func.avg(QueryLog.latency_ms))) or 0.0
    positive = (
        await db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.feedback == 1))
        or 0
    )
    negative = (
        await db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.feedback == 0))
        or 0
    )
    return AnalyticsStats(
        total_queries=total,
        avg_faithfulness=round(float(avg_faith), 3),
        insufficient_context_rate=round(no_context / total, 3) if total else 0.0,
        avg_latency_ms=round(float(avg_latency), 1),
        feedback_positive=positive,
        feedback_negative=negative,
    )


@router.get("/recent-queries", response_model=list[RecentQueryItem])
async def recent_queries(
    db: DbDep,
    current_user: UserDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[RecentQueryItem]:
    """Son sorgu loglarını en yeniden eskiye döndürür."""
    rows = (
        (await db.execute(select(QueryLog).order_by(QueryLog.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [RecentQueryItem.model_validate(r) for r in rows]


@router.get("/top-queries", response_model=list[TopQueryItem])
async def top_queries(db: DbDep, current_user: UserDep) -> list[TopQueryItem]:
    """En çok sorulan 10 sorguyu sayılarıyla döndürür."""
    rows = (
        await db.execute(
            select(QueryLog.query, func.count().label("count"))
            .group_by(QueryLog.query)
            .order_by(func.count().desc())
            .limit(10)
        )
    ).all()
    return [TopQueryItem(query=query, count=count) for query, count in rows]
