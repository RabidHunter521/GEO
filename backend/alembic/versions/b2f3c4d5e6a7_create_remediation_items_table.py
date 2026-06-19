"""create_remediation_items_table

Revision ID: b2f3c4d5e6a7
Revises: a1f2b3c4d5e6
Create Date: 2026-06-19 12:41:00.000000

Tracks the "Flagged -> In progress -> Corrected" remediation loop for
hallucinations and competitor-won queries, persisted per client so progress
survives across scans.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2f3c4d5e6a7'
down_revision: Union[str, None] = 'a1f2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'remediation_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('item_type', sa.String(length=32), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False, server_default=''),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='flagged'),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('client_id', 'item_type', 'platform', 'label', name='uq_remediation_dedupe'),
    )
    op.create_index('ix_remediation_items_client_id', 'remediation_items', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_remediation_items_client_id', table_name='remediation_items')
    op.drop_table('remediation_items')
