"""create_dimension_assessments_table

Revision ID: a2b3c4d5e6f7
Revises: b2f3c4d5e6a7
Create Date: 2026-06-21 08:20:00.000000

Stores Claude-suggested, admin-reviewed scores + evidence for the manual GEO
dimensions (brand_authority, content_quality).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'b2f3c4d5e6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dimension_assessments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('dimension', sa.String(length=32), nullable=False),
        sa.Column('suggested_score', sa.Integer(), nullable=False),
        sa.Column('final_score', sa.Integer(), nullable=True),
        sa.Column('evidence_bullets', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('raw_narrative', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='suggested'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dimension_assessments_client_id', 'dimension_assessments', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_dimension_assessments_client_id', table_name='dimension_assessments')
    op.drop_table('dimension_assessments')
