"""add share link expiry to clients

Optional expiry for the read-only client view link. NULL = never expires,
so existing links keep working. clients already has RLS enabled.

Revision ID: 283e6ea1f8c7
Revises: 12960c0a6720
Create Date: 2026-09-30 07:15:59.288140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '283e6ea1f8c7'
down_revision: Union[str, None] = '12960c0a6720'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("share_token_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "share_token_expires_at")
