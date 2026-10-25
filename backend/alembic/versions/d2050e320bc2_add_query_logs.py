"""add query_logs

Revision ID: d2050e320bc2
Revises: dc2bcee4643e
Create Date: 2026-10-24 16:52:58.978341

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2050e320bc2"
down_revision: str | None = "dc2bcee4643e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Analitik panosu: her chat isteğinin metrikleri (feedback sonradan doldurulur).
    op.create_table(
        "query_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column(
            "had_context",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("feedback", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("query_logs")
