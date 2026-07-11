"""create_action_recommendations_table

Revision ID: c9d1e2f3a4b5
Revises: f8a9b0c1d2e3
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_recommendations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('geo_score_id', sa.UUID(), nullable=True),
        sa.Column('action_text', sa.Text(), nullable=False),
        sa.Column('dimension', sa.String(length=40), nullable=False),
        sa.Column('estimated_impact', sa.Float(), nullable=False, server_default='0'),
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['geo_score_id'], ['geo_scores.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_action_recommendations_client_id', 'action_recommendations', ['client_id']
    )


def downgrade() -> None:
    op.drop_index('ix_action_recommendations_client_id', table_name='action_recommendations')
    op.drop_table('action_recommendations')
