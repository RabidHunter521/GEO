"""add site audits and llms full

Revision ID: 51b4eb5916db
Revises: e5f0a7b4c9d3
Create Date: 2026-07-22 23:40:35.819028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '51b4eb5916db'
down_revision: Union[str, None] = 'e5f0a7b4c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_audits_client_id", "site_audits", ["client_id"])
    op.execute("ALTER TABLE site_audits ENABLE ROW LEVEL SECURITY;")
    op.add_column("toolkit_files", sa.Column("llms_full_txt", sa.Text(), nullable=True))
    op.add_column(
        "toolkit_files",
        sa.Column("llms_full_verified", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("toolkit_files", "llms_full_verified")
    op.drop_column("toolkit_files", "llms_full_txt")
    op.execute("ALTER TABLE site_audits DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_site_audits_client_id", table_name="site_audits")
    op.drop_table("site_audits")
