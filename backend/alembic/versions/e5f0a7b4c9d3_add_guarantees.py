"""add guarantees table

Revision ID: e5f0a7b4c9d3
Revises: d4e9f6a3b8c2
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f0a7b4c9d3'
down_revision: Union[str, None] = 'd4e9f6a3b8c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guarantees",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False, server_default="ai_citability"),
        sa.Column("baseline_value", sa.Integer(), nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_state", sa.String(24), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guarantees_client_id", "guarantees", ["client_id"])
    op.execute("ALTER TABLE guarantees ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE guarantees DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_guarantees_client_id", table_name="guarantees")
    op.drop_table("guarantees")
