"""add work log entries

Revision ID: de87b61a859c
Revises: dd8483cfad4a
Create Date: 2026-07-24 11:19:49.335958

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'de87b61a859c'
down_revision: Union[str, None] = 'dd8483cfad4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_log_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="auto"),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="suggested"),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_log_entries_client_id", "work_log_entries", ["client_id"])
    op.create_index(
        "uq_work_log_entries_client_source_ref", "work_log_entries", ["client_id", "source_ref"],
        unique=True, postgresql_where=sa.text("source_ref IS NOT NULL"),
    )
    op.execute("ALTER TABLE work_log_entries ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE work_log_entries DISABLE ROW LEVEL SECURITY;")
    op.drop_index("uq_work_log_entries_client_source_ref", table_name="work_log_entries")
    op.drop_index("ix_work_log_entries_client_id", table_name="work_log_entries")
    op.drop_table("work_log_entries")
