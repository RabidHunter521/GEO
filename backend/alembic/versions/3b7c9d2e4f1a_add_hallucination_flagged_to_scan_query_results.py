"""add_hallucination_flagged_to_scan_query_results

Revision ID: 3b7c9d2e4f1a
Revises: 0ef658851600
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3b7c9d2e4f1a'
down_revision: Union[str, None] = '0ef658851600'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'scan_query_results',
        sa.Column('hallucination_flagged', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('scan_query_results', 'hallucination_flagged')
