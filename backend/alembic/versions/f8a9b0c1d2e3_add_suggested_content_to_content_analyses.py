"""add_suggested_content_to_content_analyses

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'content_analyses',
        sa.Column('suggested_content_json', postgresql.JSONB(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('content_analyses', 'suggested_content_json')
