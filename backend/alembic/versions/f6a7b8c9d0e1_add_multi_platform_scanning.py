"""add_multi_platform_scanning

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALL_PLATFORMS_JSON = '\'["chatgpt", "perplexity", "gemini", "claude"]\''


def upgrade() -> None:
    # server_default backfills existing single-platform rows as gemini
    op.add_column(
        'scan_query_results',
        sa.Column('platform', sa.String(length=50), nullable=False, server_default='gemini'),
    )
    op.add_column(
        'clients',
        sa.Column('enabled_platforms', sa.JSON(), nullable=False, server_default=sa.text(_ALL_PLATFORMS_JSON)),
    )
    op.add_column(
        'geo_scores',
        sa.Column('platform_breakdown', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('geo_scores', 'platform_breakdown')
    op.drop_column('clients', 'enabled_platforms')
    op.drop_column('scan_query_results', 'platform')
