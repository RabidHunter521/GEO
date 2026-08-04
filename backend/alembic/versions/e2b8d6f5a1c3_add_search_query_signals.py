"""add search query signals: normalized Google Search Console import layer (Phase 5 Task 5)

Persists `search_query_signals`, a tenant-scoped, deduplicated daily import
of Google Search Console performance rows. This is NOT a raw Google data
mirror and stores no OAuth/refresh tokens — the sync endpoint
(`app.api.v1.search_console`) receives already-fetched rows and this table
just normalizes them for evidence correlation (tracked-query visibility,
conversion events) in later Phase 5 tasks.

Kept as its own migration (rather than extending d1a7c5f4e0b2, which its own
docstring says Task 5 would extend) because Task 6 (conversion_events) is
being built in parallel against the same parent revision — two agents
editing one migration file concurrently is a worse failure mode than two
sibling migrations sharing a down_revision, which `alembic merge` (or a
follow-up migration with two down_revisions) resolves cleanly later.

The unique index is a plain (non-partial) unique index — unlike
`tracked_queries`, every column in the identity tuple is NOT NULL with a
default, so there is no NULL-distinctness hazard requiring a partial index.

Revision ID: e2b8d6f5a1c3
Revises: d1a7c5f4e0b2
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2b8d6f5a1c3"
down_revision: Union[str, None] = "d1a7c5f4e0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_query_signals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("property_uri", sa.String(length=255), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("query", sa.String(length=2000), nullable=False),
        sa.Column("page", sa.String(length=2000), nullable=False),
        sa.Column("country", sa.String(length=3), nullable=False, server_default="ZZZ"),
        sa.Column("device", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position", sa.Float(), nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "uq_search_query_signals_identity",
        "search_query_signals",
        ["client_id", "property_uri", "signal_date", "query", "page", "country", "device"],
        unique=True,
    )
    op.create_index(
        "ix_search_query_signals_client_date",
        "search_query_signals",
        ["client_id", sa.text("signal_date DESC")],
    )
    op.create_index(
        "ix_search_query_signals_client_query_date",
        "search_query_signals",
        ["client_id", "query", sa.text("signal_date DESC")],
    )

    op.execute("ALTER TABLE search_query_signals ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE search_query_signals FROM anon;")


def downgrade() -> None:
    op.execute("ALTER TABLE search_query_signals DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_search_query_signals_client_query_date", table_name="search_query_signals")
    op.drop_index("ix_search_query_signals_client_date", table_name="search_query_signals")
    op.drop_index("uq_search_query_signals_identity", table_name="search_query_signals")
    op.drop_table("search_query_signals")
