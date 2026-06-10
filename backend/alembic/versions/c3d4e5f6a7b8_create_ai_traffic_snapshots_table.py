"""create_ai_traffic_snapshots_table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-10 00:00:03.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_traffic_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('ai_visitors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', 'period', name='uq_ai_traffic_snapshots_client_period'),
    )
    op.create_index(
        'ix_ai_traffic_snapshots_client_id', 'ai_traffic_snapshots', ['client_id']
    )


def downgrade() -> None:
    op.drop_index('ix_ai_traffic_snapshots_client_id', table_name='ai_traffic_snapshots')
    op.drop_table('ai_traffic_snapshots')
