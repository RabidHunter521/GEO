"""add measurement and business proof: governed query universe (Phase 5 Task 1)

Persists the governed, durable query universe (`tracked_queries`) that
repeated samples attach to, and adds sample metadata to `scan_query_results`
so a stability calculation (Phase 5 Task 4) can group observations of the
same tracked query across scans instead of treating every scan row as an
independent, unrelated event.

Two partial unique indexes enforce dedup separately for brand-level queries
(location_id IS NULL) and location-level queries (location_id IS NOT NULL) —
a plain UNIQUE(client_id, location_id, normalized_text) would not work
because Postgres treats NULL as distinct in a unique constraint, silently
allowing duplicate brand-level rows. They are created with raw `op.execute`
SQL (not `op.create_index(postgresql_where=...)`) since the partial-index
WHERE clause is Postgres-only syntax and this keeps that fact explicit at
the call site.

This migration is later extended by Task 5 (search_query_signals) and
Task 6 (conversion_events) — both add their own tables here rather than in
new migration files, per the Phase 5 plan.

Revision ID: d1a7c5f4e0b2
Revises: c0f6b4e3d9a1
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1a7c5f4e0b2"
down_revision: Union[str, None] = "c0f6b4e3d9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_queries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("intent", sa.String(length=32), nullable=False),
        sa.Column("buyer_stage", sa.String(length=32), nullable=True),
        sa.Column("service_key", sa.String(length=64), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="standard"),
        sa.Column("demand_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "demand_weight >= 0", name="ck_tracked_queries_demand_weight_non_negative"
        ),
        sa.CheckConstraint(
            "priority_score >= 0", name="ck_tracked_queries_priority_score_non_negative"
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["location_id", "client_id"],
            ["business_locations.id", "business_locations.client_id"],
            name="fk_tracked_queries_location_client",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Partial unique indexes — Postgres-only WHERE clause, written as raw SQL
    # (not the SQLAlchemy create_index dialect-kwarg form) to keep that fact
    # explicit rather than implicit in an argument name.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_tracked_query_brand
        ON tracked_queries (client_id, normalized_text)
        WHERE location_id IS NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_tracked_query_location
        ON tracked_queries (client_id, location_id, normalized_text)
        WHERE location_id IS NOT NULL;
        """
    )

    op.create_index(
        "ix_tracked_queries_client_active_priority",
        "tracked_queries",
        ["client_id", "is_active", sa.text("priority_score DESC")],
    )
    op.create_index(
        "ix_tracked_queries_client_location_intent",
        "tracked_queries",
        ["client_id", "location_id", "intent"],
    )

    op.execute("ALTER TABLE tracked_queries ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE tracked_queries FROM anon;")

    # --- scan_query_results: repeated-sample metadata ---------------------
    op.add_column(
        "scan_query_results",
        sa.Column("tracked_query_id", sa.UUID(), nullable=True),
    )
    # SET NULL, not CASCADE: a deleted/archived tracked query must not erase
    # the historical scan rows it produced. query_text already retains the
    # original wording independent of this link.
    op.create_foreign_key(
        "fk_scan_query_results_tracked_query",
        "scan_query_results",
        "tracked_queries",
        ["tracked_query_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "scan_query_results",
        sa.Column("sample_index", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_scan_query_results_sample_index_positive",
        "scan_query_results",
        "sample_index > 0",
    )
    op.add_column(
        "scan_query_results",
        sa.Column("prompt_version", sa.String(length=32), nullable=False, server_default="v1"),
    )
    # Underlying AI model that produced response_text (e.g. "gpt-4o"), distinct
    # from `platform` (the product/vendor surface: chatgpt, perplexity, gemini,
    # claude). Legacy rows predate per-sample model tracking, so they backfill
    # to "unknown" rather than a guessed value.
    op.add_column(
        "scan_query_results",
        sa.Column("model_name", sa.String(length=100), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "scan_query_results",
        sa.Column("model_version", sa.String(length=100), nullable=True),
    )
    # observed_at backfills from the row's own created_at (its true historical
    # observation time) rather than NOW(), which would make every pre-Phase-5
    # row look like it was observed the moment this migration ran.
    op.add_column(
        "scan_query_results",
        sa.Column("observed_at", sa.DateTime(), nullable=True),
    )
    op.execute("UPDATE scan_query_results SET observed_at = created_at WHERE observed_at IS NULL")
    op.alter_column(
        "scan_query_results",
        "observed_at",
        nullable=False,
        server_default=sa.text("now()"),
    )

    op.create_index(
        "ix_scan_query_results_tracked_query_observed",
        "scan_query_results",
        ["tracked_query_id", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_scan_query_results_scan_tracked_sample",
        "scan_query_results",
        ["scan_id", "tracked_query_id", "sample_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_query_results_scan_tracked_sample", table_name="scan_query_results")
    op.drop_index("ix_scan_query_results_tracked_query_observed", table_name="scan_query_results")

    op.drop_column("scan_query_results", "observed_at")
    op.drop_column("scan_query_results", "model_version")
    op.drop_column("scan_query_results", "model_name")
    op.drop_column("scan_query_results", "prompt_version")
    op.drop_constraint(
        "ck_scan_query_results_sample_index_positive", "scan_query_results", type_="check"
    )
    op.drop_column("scan_query_results", "sample_index")
    op.drop_constraint(
        "fk_scan_query_results_tracked_query", "scan_query_results", type_="foreignkey"
    )
    op.drop_column("scan_query_results", "tracked_query_id")

    op.execute("ALTER TABLE tracked_queries DISABLE ROW LEVEL SECURITY;")

    op.drop_index("ix_tracked_queries_client_location_intent", table_name="tracked_queries")
    op.drop_index("ix_tracked_queries_client_active_priority", table_name="tracked_queries")
    op.drop_index("uq_tracked_query_location", table_name="tracked_queries")
    op.drop_index("uq_tracked_query_brand", table_name="tracked_queries")
    op.drop_table("tracked_queries")
