"""create_content_analyses_table

Revision ID: c5d6e7f8a9b0
Revises: 3b7c9d2e4f1a
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = '3b7c9d2e4f1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'content_analyses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('topics_json', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('entities_json', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('entity_coverage_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('content_metrics_json', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('content_quality_recommendation', sa.Text(), nullable=True),
        sa.Column('pages_crawled', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('analyzed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_content_analyses_client_id', 'content_analyses', ['client_id']
    )


def downgrade() -> None:
    op.drop_index('ix_content_analyses_client_id', table_name='content_analyses')
    op.drop_table('content_analyses')
