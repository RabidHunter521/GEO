"""add benchmark data moat: cohorts, private membership, immutable snapshots (Phase 6 Task 1)

Persists the three tables the benchmark engine is built on:

* `benchmark_cohorts` — versioned definitions of "who is comparable to whom".
* `benchmark_cohort_memberships` — the private, per-period record of which
  clients counted and why the rest did not. This is the only table in Phase 6
  that maps an aggregate back to identifiable organizations and it is never
  reachable from a client or public schema.
* `benchmark_snapshots` — immutable aggregate results.

The privacy rules live in CHECK constraints rather than only in the services
that write these rows. A suppressed snapshot that still carries a p50 would be
rendered by every downstream reader that trusts the flag, and an exclusion with
no recorded reason is indistinguishable from a bug — neither should be
representable.

Approved snapshots are protected twice: the plpgsql trigger installed here
covers everything that can reach the table, and an ORM guard in
`app/models/benchmark_snapshot.py` covers application writes so the rule is
testable on the SQLite suite and raises a domain error. Both read the same
`approved_at` value so they cannot drift.

Chains from a4b5c6d7e8f9 (Phase 5's merge revision), not the d1a7c5f4e0b2 the
plan named — the plan predates Phase 5 shipping, and chaining there would fork
the tree into two heads.

Revision ID: e2b8d6a5f1c3
Revises: a4b5c6d7e8f9
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2b8d6a5f1c3"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMMUTABILITY_FUNCTION = """
CREATE OR REPLACE FUNCTION reject_approved_benchmark_snapshot_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.approved_at IS NOT NULL THEN
        RAISE EXCEPTION
            'benchmark_snapshots row % is approved and immutable; '
            'write a new calculation_version instead', OLD.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "benchmark_cohorts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cohort_key", sa.String(length=255), nullable=False),
        sa.Column("definition_version", sa.String(length=16), nullable=False),
        sa.Column("industry_pack", sa.String(length=32), nullable=False),
        sa.Column("subcategory", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("market_area", sa.String(length=64), nullable=True),
        sa.Column("scale_band", sa.String(length=32), nullable=False),
        sa.Column("coverage_band", sa.String(length=32), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("min_member_count", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        # The plan's floor. The minimum cohort size is configurable upward only;
        # lowering it is the single change that would turn every correct
        # suppression into a publishable number, so it is not representable.
        sa.CheckConstraint(
            "min_member_count >= 10",
            name="ck_benchmark_cohorts_min_member_count_floor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cohort_key", "definition_version", name="uq_benchmark_cohorts_key_version"
        ),
    )
    op.create_index(
        "ix_benchmark_cohorts_pack_country_scale_active",
        "benchmark_cohorts",
        ["industry_pack", "country_code", "scale_band", "is_active"],
    )

    op.create_table(
        "benchmark_cohort_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cohort_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_period_start", sa.Date(), nullable=False),
        sa.Column("evaluation_period_end", sa.Date(), nullable=False),
        sa.Column("is_included", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("measurement_coverage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "is_included OR exclusion_reason IS NOT NULL",
            name="ck_benchmark_cohort_memberships_exclusion_has_reason",
        ),
        sa.CheckConstraint(
            "NOT is_included OR exclusion_reason IS NULL",
            name="ck_benchmark_cohort_memberships_inclusion_has_no_reason",
        ),
        sa.CheckConstraint(
            "measurement_coverage >= 0",
            name="ck_benchmark_cohort_memberships_coverage_non_negative",
        ),
        sa.CheckConstraint(
            "evaluation_period_start <= evaluation_period_end",
            name="ck_benchmark_cohort_memberships_period_ordered",
        ),
        sa.ForeignKeyConstraint(["cohort_id"], ["benchmark_cohorts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cohort_id",
            "client_id",
            "evaluation_period_start",
            "evaluation_period_end",
            name="uq_benchmark_cohort_memberships_cohort_client_period",
        ),
    )
    op.create_index(
        "ix_benchmark_cohort_memberships_client_period",
        "benchmark_cohort_memberships",
        ["client_id", sa.text("evaluation_period_end DESC")],
    )

    op.create_table(
        "benchmark_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cohort_id", sa.UUID(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metric_key", sa.String(length=64), nullable=False),
        sa.Column("calculation_version", sa.String(length=16), nullable=False),
        sa.Column("eligible_member_count", sa.Integer(), nullable=False),
        sa.Column("contributing_member_count", sa.Integer(), nullable=False),
        sa.Column("p25", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("p50", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("p75", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("mean", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("suppression_reason", sa.String(length=64), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        # Suppression and the aggregate columns are strictly biconditional.
        sa.CheckConstraint(
            "NOT suppressed OR (p25 IS NULL AND p50 IS NULL AND p75 IS NULL AND mean IS NULL)",
            name="ck_benchmark_snapshots_suppressed_has_no_values",
        ),
        sa.CheckConstraint(
            "suppressed OR "
            "(p25 IS NOT NULL AND p50 IS NOT NULL AND p75 IS NOT NULL AND mean IS NOT NULL)",
            name="ck_benchmark_snapshots_unsuppressed_has_values",
        ),
        sa.CheckConstraint(
            "p25 IS NULL OR (p25 <= p50 AND p50 <= p75)",
            name="ck_benchmark_snapshots_percentiles_ordered",
        ),
        sa.CheckConstraint(
            "contributing_member_count <= eligible_member_count",
            name="ck_benchmark_snapshots_contributing_within_eligible",
        ),
        sa.CheckConstraint(
            "eligible_member_count >= 0 AND contributing_member_count >= 0",
            name="ck_benchmark_snapshots_counts_non_negative",
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name="ck_benchmark_snapshots_period_ordered",
        ),
        # RESTRICT, not CASCADE: an approved aggregate outlives cohort
        # housekeeping, so removing a cohort that still has snapshots has to be
        # a deliberate act rather than a side effect.
        sa.ForeignKeyConstraint(["cohort_id"], ["benchmark_cohorts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cohort_id",
            "period_start",
            "period_end",
            "metric_key",
            "calculation_version",
            name="uq_benchmark_snapshots_cohort_period_metric_version",
        ),
    )
    op.create_index(
        "ix_benchmark_snapshots_cohort_period_metric",
        "benchmark_snapshots",
        ["cohort_id", sa.text("period_end DESC"), "metric_key"],
    )

    op.execute(IMMUTABILITY_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER trg_benchmark_snapshots_reject_approved_update
        BEFORE UPDATE ON benchmark_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_approved_benchmark_snapshot_change();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_benchmark_snapshots_reject_approved_delete
        BEFORE DELETE ON benchmark_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_approved_benchmark_snapshot_change();
        """
    )

    # Opting out removes a client from cohorts in both directions: they stop
    # contributing to peer aggregates and stop receiving a comparison.
    op.add_column(
        "clients",
        sa.Column(
            "benchmark_opt_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "benchmark_publications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("edition", sa.String(length=64), nullable=False),
        sa.Column("methodology_version", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("generated_by", sa.String(length=128), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'published', 'withdrawn')",
            name="ck_benchmark_publications_status_vocabulary",
        ),
        # Separation of duty. A single shared admin API key means this cannot
        # be an authentication boundary; it is a procedural one the database
        # will not let an operator skip.
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by <> generated_by",
            name="ck_benchmark_publications_approver_differs_from_generator",
        ),
        sa.CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_benchmark_publications_approved_records_actor",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_benchmark_publications_published_was_approved",
        ),
        sa.CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_benchmark_publications_withdrawn_records_time",
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name="ck_benchmark_publications_period_ordered",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_benchmark_publications_slug"),
    )
    op.create_index(
        "ix_benchmark_publications_status_period",
        "benchmark_publications",
        ["status", "period_end"],
    )

    # Written out rather than looped: this is the security control CI checks
    # (`relrowsecurity` on every table), and it should stay greppable.
    op.execute("ALTER TABLE benchmark_cohorts ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE benchmark_cohorts FROM anon;")
    op.execute("ALTER TABLE benchmark_cohort_memberships ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE benchmark_cohort_memberships FROM anon;")
    op.execute("ALTER TABLE benchmark_snapshots ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE benchmark_snapshots FROM anon;")
    # Anonymous readers never touch this table directly. A published edition is
    # served only through the rate-limited FastAPI endpoint, which returns the
    # reviewed payload and nothing else.
    op.execute("ALTER TABLE benchmark_publications ENABLE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON TABLE benchmark_publications FROM anon;")


def downgrade() -> None:
    op.drop_column("clients", "benchmark_opt_out")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_benchmark_snapshots_reject_approved_delete "
        "ON benchmark_snapshots;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_benchmark_snapshots_reject_approved_update "
        "ON benchmark_snapshots;"
    )

    op.execute("ALTER TABLE benchmark_publications DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE benchmark_snapshots DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE benchmark_cohort_memberships DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE benchmark_cohorts DISABLE ROW LEVEL SECURITY;")

    op.drop_index(
        "ix_benchmark_publications_status_period", table_name="benchmark_publications"
    )
    op.drop_table("benchmark_publications")

    # Snapshots first: their cohort_id is RESTRICT, so dropping cohorts while
    # snapshot rows still reference them fails on a populated database.
    op.drop_index(
        "ix_benchmark_snapshots_cohort_period_metric", table_name="benchmark_snapshots"
    )
    op.drop_table("benchmark_snapshots")

    op.drop_index(
        "ix_benchmark_cohort_memberships_client_period",
        table_name="benchmark_cohort_memberships",
    )
    op.drop_table("benchmark_cohort_memberships")

    op.drop_index(
        "ix_benchmark_cohorts_pack_country_scale_active", table_name="benchmark_cohorts"
    )
    op.drop_table("benchmark_cohorts")

    op.execute("DROP FUNCTION IF EXISTS reject_approved_benchmark_snapshot_change();")
