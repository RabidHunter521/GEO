"""add_share_token_to_clients

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('share_token', sa.String(length=64), nullable=True))
    op.add_column('clients', sa.Column('share_token_created_at', sa.DateTime(), nullable=True))
    op.create_index('ix_clients_share_token', 'clients', ['share_token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_clients_share_token', table_name='clients')
    op.drop_column('clients', 'share_token_created_at')
    op.drop_column('clients', 'share_token')
