"""add outcome actions

Revision ID: a8d4f2c1b7e9
Revises: d3f7a1c58e02
Create Date: 2026-07-31 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a8d4f2c1b7e9"
down_revision: Union[str, None] = "d3f7a1c58e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outcome_actions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=True),
        sa.Column("work_log_entry_id", sa.UUID(), nullable=True),
        sa.Column("content_deliverable_id", sa.UUID(), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=256), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=True),
        sa.Column("priority_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="recommended"),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("destination_url", sa.String(length=1024), nullable=True),
        sa.Column("client_safe_summary", sa.Text(), nullable=True),
        sa.Column("approval_token_hash", sa.String(length=64), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(), nullable=True),
        sa.Column("client_decision", sa.String(length=32), nullable=True),
        sa.Column("client_comment", sa.Text(), nullable=True),
        sa.Column("client_decided_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verification_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["work_log_entry_id"], ["work_log_entries.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["content_deliverable_id"], ["content_deliverables.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_outcome_actions_client_source_ref", "outcome_actions", ["client_id", "source_ref"],
        unique=True, postgresql_where=sa.text("source_ref IS NOT NULL"),
    )
    op.create_index(
        "uq_outcome_actions_approval_token_hash", "outcome_actions", ["approval_token_hash"],
        unique=True, postgresql_where=sa.text("approval_token_hash IS NOT NULL"),
    )
    op.create_index("ix_outcome_actions_client_status", "outcome_actions", ["client_id", "status"])
    op.create_index("ix_outcome_actions_due_date", "outcome_actions", ["due_date"])
    op.execute("ALTER TABLE outcome_actions ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE outcome_actions FROM anon;")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE policy_name text;
        BEGIN
          FOR policy_name IN
            SELECT policyname FROM pg_policies
            WHERE schemaname = 'public' AND tablename = 'outcome_actions'
          LOOP
            EXECUTE format('DROP POLICY %I ON outcome_actions', policy_name);
          END LOOP;
        END $$;
        """
    )
    op.execute("ALTER TABLE outcome_actions DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_outcome_actions_due_date", table_name="outcome_actions")
    op.drop_index("ix_outcome_actions_client_status", table_name="outcome_actions")
    op.drop_index("uq_outcome_actions_approval_token_hash", table_name="outcome_actions")
    op.drop_index("uq_outcome_actions_client_source_ref", table_name="outcome_actions")
    op.drop_table("outcome_actions")
