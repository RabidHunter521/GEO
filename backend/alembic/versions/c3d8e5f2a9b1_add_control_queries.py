"""add control_queries table and scan_query_results.is_control

Revision ID: c3d8e5f2a9b1
Revises: e8f9a0b1c2d3
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d8e5f2a9b1'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_queries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="recommendation"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_control_queries_client_id", "control_queries", ["client_id"])
    op.execute("ALTER TABLE control_queries ENABLE ROW LEVEL SECURITY;")
    op.add_column(
        "scan_query_results",
        sa.Column("is_control", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("scan_query_results", "is_control")
    op.execute("ALTER TABLE control_queries DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_control_queries_client_id", table_name="control_queries")
    op.drop_table("control_queries")
