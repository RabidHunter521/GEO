"""add_recommendation_position_to_scan_query_results

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-10 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scan_query_results',
        sa.Column('recommendation_position', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('scan_query_results', 'recommendation_position')
