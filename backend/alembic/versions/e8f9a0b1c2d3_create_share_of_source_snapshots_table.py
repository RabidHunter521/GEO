"""create share_of_source_snapshots table

Revision ID: e8f9a0b1c2d3
Revises: a1b2c3d4e5f6
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_of_source_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("total_third_party_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_share_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("competitor_shares", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("acquisition_list", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", name="uq_share_of_source_snapshots_scan_id"),
    )
    op.create_index(
        "ix_share_of_source_snapshots_client_id", "share_of_source_snapshots", ["client_id"]
    )
    op.execute("ALTER TABLE share_of_source_snapshots ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE share_of_source_snapshots DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_share_of_source_snapshots_client_id", table_name="share_of_source_snapshots")
    op.drop_table("share_of_source_snapshots")
