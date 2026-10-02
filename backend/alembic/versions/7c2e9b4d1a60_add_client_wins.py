"""add client_wins table and clients.win_notifications_enabled

Client win notifications ("ChatGPT now recommends you for ..."). Every
confirmed win is recorded in client_wins; the per-client switch decides
whether the client is told. Off by default, so no existing client receives
anything until an admin turns it on.

Revision ID: 7c2e9b4d1a60
Revises: 344f3422e114
Create Date: 2026-10-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7c2e9b4d1a60'
down_revision: Union[str, None] = '344f3422e114'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column(
            "win_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "client_wins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("recommendation_position", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("channels", sa.String(64), nullable=True),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_client_wins_client_detected", "client_wins", ["client_id", "detected_at"]
    )
    # RLS inline, guarded anon revoke (CLAUDE.md §8): the Railway database has
    # no anon role, so a bare REVOKE would fail the boot-time upgrade.
    op.execute("ALTER TABLE client_wins ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') "
        "THEN EXECUTE 'REVOKE ALL ON TABLE client_wins FROM anon'; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_index("ix_client_wins_client_detected", table_name="client_wins")
    op.drop_table("client_wins")
    op.drop_column("clients", "win_notifications_enabled")
