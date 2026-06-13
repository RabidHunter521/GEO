"""create_content_briefs_table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'content_briefs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scan_query_result_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('scan_query_results.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('competitors_seen', sa.JSON(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('angle', sa.Text(), nullable=False),
        sa.Column('outline', sa.JSON(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_content_briefs_client_id', 'content_briefs', ['client_id'])
    # Missing since the original scans schema; speeds up every per-scan results query
    op.create_index('ix_scan_query_results_scan_id', 'scan_query_results', ['scan_id'])


def downgrade() -> None:
    op.drop_index('ix_scan_query_results_scan_id', table_name='scan_query_results')
    op.drop_index('ix_content_briefs_client_id', table_name='content_briefs')
    op.drop_table('content_briefs')
