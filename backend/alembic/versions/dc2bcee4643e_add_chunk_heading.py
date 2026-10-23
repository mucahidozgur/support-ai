"""add chunk heading

Revision ID: dc2bcee4643e
Revises: 49bd3bffaafd
Create Date: 2026-10-23 07:26:01.605175

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dc2bcee4643e"
down_revision: str | None = "49bd3bffaafd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Hiyerarşik chunking: chunk'ın başlık zinciri. Mevcut satırlar için NULL
    # bırakılır (yeniden index'leme ile dolar).
    op.add_column("chunks", sa.Column("heading", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "heading")
