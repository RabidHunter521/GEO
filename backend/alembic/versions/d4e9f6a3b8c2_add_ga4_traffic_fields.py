"""add ga4 traffic fields: clients.ga4_property_id, ai_traffic_snapshots.source/breakdown

Revision ID: d4e9f6a3b8c2
Revises: c3d8e5f2a9b1
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4e9f6a3b8c2'
down_revision: Union[str, None] = 'c3d8e5f2a9b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("ga4_property_id", sa.String(32), nullable=True))
    op.add_column(
        "ai_traffic_snapshots",
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
    )
    op.add_column(
        "ai_traffic_snapshots",
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_traffic_snapshots", "breakdown")
    op.drop_column("ai_traffic_snapshots", "source")
    op.drop_column("clients", "ga4_property_id")
