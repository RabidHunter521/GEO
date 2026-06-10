"""add_manual_score_evidence_to_clients

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-10 00:00:02.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('brand_authority_evidence', sa.Text(), nullable=True))
    op.add_column('clients', sa.Column('content_quality_evidence', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'content_quality_evidence')
    op.drop_column('clients', 'brand_authority_evidence')
