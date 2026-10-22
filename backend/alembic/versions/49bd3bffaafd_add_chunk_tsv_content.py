"""add chunk tsv_content

Revision ID: 49bd3bffaafd
Revises: 475b837a3780
Create Date: 2026-10-22 16:06:49.605035

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "49bd3bffaafd"
down_revision: str | None = "475b837a3780"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # FTS (BM25) araması: content'ten türetilen generated tsvector kolonu.
    # GIN index'i @@ aramalarını hızlandırır (5.000+ KB makalesi hedefi).
    op.add_column(
        "chunks",
        sa.Column(
            "tsv_content",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_tsv_content", "chunks", ["tsv_content"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunks_tsv_content", table_name="chunks", postgresql_using="gin")
    op.drop_column("chunks", "tsv_content")
