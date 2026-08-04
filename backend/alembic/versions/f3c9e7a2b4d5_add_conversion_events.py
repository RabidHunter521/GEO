"""add conversion events: normalized, evidence-labeled business outcomes (Phase 5 Task 6)

Persists `conversion_events` — the tenant-scoped ledger that normalizes
heterogeneous business-outcome sources (GA4 exports, CRM webhooks,
call-tracking platforms, booking systems, manual admin entry) into one
shape, tagged with an explicit `evidence_level` (observed / attributed /
assisted / estimated) so a client report can never quietly collapse "we
watched this happen" and "we modeled this" into a single undifferentiated
number.

Built on its own migration head (down_revision points at d1a7c5f4e0b2, the
Task 1 migration) rather than extending d1a7c5f4e0b2 in place, because Task 5
(search_query_signals) is being built in parallel against the same parent
revision. This intentionally produces two heads
(e2b8d6f5a1c3 from Task 5, f3c9e7a2b4d5 here) until a follow-up merge
migration reconciles them — see the Phase 5 plan.

Revision ID: f3c9e7a2b4d5
Revises: d1a7c5f4e0b2
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f3c9e7a2b4d5"
down_revision: Union[str, None] = "d1a7c5f4e0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversion_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("evidence_level", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("value_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="MYR"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("calculation_method", sa.String(length=64), nullable=True),
        sa.Column("calculation_version", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "value_minor >= 0 OR evidence_level = 'estimated'",
            name="ck_conversion_events_value_minor_non_negative_unless_estimated",
        ),
        sa.CheckConstraint(
            "evidence_level != 'observed' "
            "OR (external_event_id IS NOT NULL AND occurred_at IS NOT NULL)",
            name="ck_conversion_events_observed_requires_source_and_time",
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id"], ["business_locations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Partial unique index — Postgres-only WHERE clause, written as raw SQL
    # (not the SQLAlchemy create_index dialect-kwarg form) to keep that fact
    # explicit at the call site, same pattern as d1a7c5f4e0b2's
    # uq_tracked_query_brand / uq_tracked_query_location.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_conversion_events_client_source_external_id
        ON conversion_events (client_id, source, external_event_id)
        WHERE external_event_id IS NOT NULL;
        """
    )

    op.create_index(
        "ix_conversion_events_client_occurred",
        "conversion_events",
        ["client_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_conversion_events_client_evidence_occurred",
        "conversion_events",
        ["client_id", "evidence_level", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_conversion_events_client_type_occurred",
        "conversion_events",
        ["client_id", "event_type", sa.text("occurred_at DESC")],
    )

    op.execute("ALTER TABLE conversion_events ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE conversion_events FROM anon;")


def downgrade() -> None:
    op.execute("ALTER TABLE conversion_events DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_conversion_events_client_type_occurred", table_name="conversion_events")
    op.drop_index("ix_conversion_events_client_evidence_occurred", table_name="conversion_events")
    op.drop_index("ix_conversion_events_client_occurred", table_name="conversion_events")
    op.drop_index(
        "uq_conversion_events_client_source_external_id", table_name="conversion_events"
    )
    op.drop_table("conversion_events")
