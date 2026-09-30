"""add share link view tracking to clients

When the client last opened their read-only view link and how many visits
they have made. clients already has RLS enabled; adding columns does not
change that.

Revision ID: 12960c0a6720
Revises: 1a3fd284901c
Create Date: 2026-09-30 07:08:42.629000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12960c0a6720'
down_revision: Union[str, None] = '1a3fd284901c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("share_last_viewed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "clients",
        sa.Column("share_view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("clients", "share_view_count")
    op.drop_column("clients", "share_last_viewed_at")
