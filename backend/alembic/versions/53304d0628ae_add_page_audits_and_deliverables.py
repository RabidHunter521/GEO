"""add page audits and deliverables

Revision ID: 53304d0628ae
Revises: 51b4eb5916db
Create Date: 2026-07-23 14:44:29.221801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '53304d0628ae'
down_revision: Union[str, None] = '51b4eb5916db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "page_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("suggestions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("suggestions_failed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_page_audits_client_id", "page_audits", ["client_id"])
    op.execute("ALTER TABLE page_audits ENABLE ROW LEVEL SECURITY;")

    op.create_table(
        "content_deliverables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_content_deliverables_client_id", "content_deliverables", ["client_id"])
    op.execute("ALTER TABLE content_deliverables ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE content_deliverables DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_content_deliverables_client_id", table_name="content_deliverables")
    op.drop_table("content_deliverables")
    op.execute("ALTER TABLE page_audits DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_page_audits_client_id", table_name="page_audits")
    op.drop_table("page_audits")
