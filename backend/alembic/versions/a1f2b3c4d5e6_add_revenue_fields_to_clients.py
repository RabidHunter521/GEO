"""add_revenue_fields_to_clients

Revision ID: a1f2b3c4d5e6
Revises: f7c4a9e2d6b1
Create Date: 2026-06-19 12:40:00.000000

Adds admin-set inputs used to turn raw AI-referral visitor counts into a single
pipeline/revenue number for the client report. avg_deal_value_rm is intentionally
nullable — there is no sane default for deal size, and the RM line only renders
once the admin sets it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, None] = 'f7c4a9e2d6b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('avg_deal_value_rm', sa.Integer(), nullable=True))
    op.add_column('clients', sa.Column('visitor_to_lead_pct', sa.Integer(), nullable=False, server_default='2'))
    op.add_column('clients', sa.Column('lead_to_customer_pct', sa.Integer(), nullable=False, server_default='20'))


def downgrade() -> None:
    op.drop_column('clients', 'lead_to_customer_pct')
    op.drop_column('clients', 'visitor_to_lead_pct')
    op.drop_column('clients', 'avg_deal_value_rm')
