"""add lead-source attribution: tracked WhatsApp link + "how did you hear" signals

Creates `attribution_settings` (one row per client: tracked-link token,
optional WhatsApp number, hashed inbound-webhook secret) and
`attribution_signals` (every WhatsApp click / heard-about-us answer, with the
AI platform matched, if any). AI-matched signals also write an `attributed`
row to `conversion_events`; that table is unchanged.

RLS is enabled inline on both tables (CLAUDE.md §8). No Supabase-role grants
are touched: the Railway database has none.

Revision ID: 43b801757a66
Revises: 344f3422e114
Create Date: 2026-10-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "43b801757a66"
down_revision: Union[str, None] = "344f3422e114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attribution_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("click_token", sa.String(length=64), nullable=False),
        sa.Column("whatsapp_number", sa.String(length=20), nullable=True),
        sa.Column("whatsapp_message", sa.Text(), nullable=True),
        sa.Column("tracking_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("webhook_secret_hash", sa.String(length=64), nullable=True),
        sa.Column("webhook_secret_created_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
        sa.UniqueConstraint("click_token"),
        sa.UniqueConstraint("webhook_secret_hash"),
    )
    op.execute("ALTER TABLE attribution_settings ENABLE ROW LEVEL SECURITY;")

    op.create_table(
        "attribution_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("ai_platform", sa.String(length=64), nullable=True),
        sa.Column("match_reason", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("raw_value", sa.String(length=500), nullable=True),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("conversion_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversion_event_id"], ["conversion_events.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id", "channel", "external_id",
            name="uq_attribution_signals_client_channel_external",
        ),
    )
    op.execute(
        "CREATE INDEX ix_attribution_signals_client_occurred "
        "ON attribution_signals (client_id, occurred_at DESC);"
    )
    op.create_index(
        "ix_attribution_signals_visitor",
        "attribution_signals",
        ["client_id", "visitor_hash", "occurred_at"],
    )
    op.execute("ALTER TABLE attribution_signals ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.drop_index("ix_attribution_signals_visitor", table_name="attribution_signals")
    op.execute("DROP INDEX IF EXISTS ix_attribution_signals_client_occurred;")
    op.drop_table("attribution_signals")
    op.drop_table("attribution_settings")
