"""create scan_query_sources table

Revision ID: 2a685d803d33
Revises: a2b3c4d5e6f7
Create Date: 2026-07-03 16:17:20.654681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2a685d803d33'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_query_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("scan_query_result_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=True),
        sa.Column("fetch_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("present_brands", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["scan_query_result_id"], ["scan_query_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_query_sources_domain", "scan_query_sources", ["domain"])
    op.create_index("ix_scan_query_sources_result_id", "scan_query_sources", ["scan_query_result_id"])


def downgrade() -> None:
    op.drop_index("ix_scan_query_sources_result_id", table_name="scan_query_sources")
    op.drop_index("ix_scan_query_sources_domain", table_name="scan_query_sources")
    op.drop_table("scan_query_sources")
