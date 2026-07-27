"""add misinformation findings

Revision ID: c7e4d1b90fa2
Revises: de87b61a859c
Create Date: 2026-07-27 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e4d1b90fa2'
down_revision: Union[str, None] = 'de87b61a859c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "misinformation_findings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("scan_query_result_id", sa.UUID(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="suggested"),
        sa.Column("detected_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_query_result_id"], ["scan_query_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_misinformation_findings_client_id", "misinformation_findings", ["client_id"]
    )
    op.execute("ALTER TABLE misinformation_findings ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE misinformation_findings DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_misinformation_findings_client_id", table_name="misinformation_findings")
    op.drop_table("misinformation_findings")
