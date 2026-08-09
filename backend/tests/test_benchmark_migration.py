"""Static checks for the Phase 6 benchmark migration.

The migration uses Postgres-only DDL (ROW LEVEL SECURITY, plpgsql triggers)
that cannot run against the SQLite test database, and `backend/.env` points at
production Supabase so a real `alembic upgrade` here would migrate production.
The project's convention — see `test_measurement_migration.py` — is therefore
to verify structure statically and run the real upgrade/downgrade against
Postgres in the `seenby-release` runbook instead.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND / "alembic" / "versions" / "e2b8d6a5f1c3_add_benchmark_data_moat.py"
)
REVISION_ID = "e2b8d6a5f1c3"
DOWN_REVISION_ID = "a4b5c6d7e8f9"

TABLES = (
    "benchmark_cohorts",
    "benchmark_cohort_memberships",
    "benchmark_snapshots",
    # Task 7 extends this same revision rather than chaining a new one: it has
    # not been applied anywhere yet, so there is no deployed schema to respect.
    "benchmark_publications",
)


def _source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_migration_file_exists():
    assert MIGRATION_PATH.exists()


def test_migration_declares_expected_revision_ids():
    source = _source()
    assert f'revision: str = "{REVISION_ID}"' in source
    assert f'down_revision: Union[str, None] = "{DOWN_REVISION_ID}"' in source


def test_migration_chains_from_phase_5_head_and_tree_does_not_fork():
    """Phase 5 ended on the merge revision a4b5c6d7e8f9, which must remain
    the direct parent of this migration. The migration is no longer the single
    chain head because later migrations extend it, but the tree must maintain
    exactly one head to prevent accidental schema drift."""
    script = _script_dir()
    revision = script.get_revision(REVISION_ID)
    assert revision is not None
    assert revision.down_revision == DOWN_REVISION_ID

    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one chain head, found {heads}"


def test_migration_creates_all_three_benchmark_tables():
    source = _source()
    for table in TABLES:
        assert f'op.create_table(\n        "{table}"' in source, f"missing table {table}"


def test_migration_declares_documented_unique_constraints():
    source = _source()
    assert "uq_benchmark_cohorts_key_version" in source
    assert "uq_benchmark_cohort_memberships_cohort_client_period" in source
    assert "uq_benchmark_snapshots_cohort_period_metric_version" in source
    assert "uq_benchmark_publications_slug" in source


def test_migration_enforces_publication_separation_of_duty():
    """A single shared admin key means this cannot be an authentication
    boundary, so the database has to be the thing that refuses it."""
    source = _source()
    assert "ck_benchmark_publications_approver_differs_from_generator" in source
    assert "approved_by IS NULL OR approved_by <> generated_by" in source


def test_migration_enforces_publication_lifecycle_invariants():
    source = _source()
    for constraint in (
        "ck_benchmark_publications_status_vocabulary",
        "ck_benchmark_publications_approved_records_actor",
        "ck_benchmark_publications_published_was_approved",
        "ck_benchmark_publications_withdrawn_records_time",
    ):
        assert constraint in source


def test_migration_declares_documented_indexes():
    source = _source()
    for index_name in (
        "ix_benchmark_cohorts_pack_country_scale_active",
        "ix_benchmark_cohort_memberships_client_period",
        "ix_benchmark_snapshots_cohort_period_metric",
    ):
        assert index_name in source


def test_migration_enforces_the_minimum_cohort_size_floor():
    source = _source()
    assert "ck_benchmark_cohorts_min_member_count_floor" in source
    assert "min_member_count >= 10" in source


def test_migration_enforces_suppression_blanks_every_aggregate():
    source = _source()
    assert "ck_benchmark_snapshots_suppressed_has_no_values" in source
    assert "ck_benchmark_snapshots_unsuppressed_has_values" in source


def test_migration_enforces_explainable_membership():
    source = _source()
    assert "ck_benchmark_cohort_memberships_exclusion_has_reason" in source


def test_migration_adds_client_benchmark_opt_out():
    source = _source()
    assert '"benchmark_opt_out"' in source
    assert "clients" in source


def test_migration_installs_approved_snapshot_immutability_trigger():
    """The ORM guard in app/models/benchmark_snapshot.py protects application
    writes; the trigger protects everything else that can reach the table."""
    source = _source()
    assert "reject_approved_benchmark_snapshot_change" in source
    assert "BEFORE UPDATE ON benchmark_snapshots" in source
    assert "BEFORE DELETE ON benchmark_snapshots" in source


def test_migration_enables_rls_and_revokes_anon_on_every_new_table():
    source = _source()
    for table in TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in source
        assert f"REVOKE ALL ON TABLE {table} FROM anon;" in source


def test_migration_grants_no_new_role_access():
    """RLS is enabled with zero policies (CLAUDE.md §8): only `postgres`
    (which bypasses RLS) connects, so this migration must not GRANT anything
    to any role — that would reopen the data-loss path d3f7a1c58e02 closed."""
    assert "GRANT " not in _source().upper()


def test_migration_defines_symmetric_upgrade_and_downgrade():
    source = _source()
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source

    downgrade_body = source.split("def downgrade() -> None:")[1]
    for table in TABLES:
        assert f'op.drop_table("{table}")' in downgrade_body
    assert 'op.drop_column("clients", "benchmark_opt_out")' in downgrade_body
    assert 'op.drop_index(\n        "ix_benchmark_publications_status_period"' in downgrade_body
    assert "DROP FUNCTION IF EXISTS reject_approved_benchmark_snapshot_change" in downgrade_body


def test_downgrade_drops_snapshots_before_the_cohorts_they_reference():
    """benchmark_snapshots.cohort_id is RESTRICT, so dropping cohorts first
    would fail on a populated database."""
    downgrade_body = _source().split("def downgrade() -> None:")[1]
    assert downgrade_body.index('op.drop_table("benchmark_snapshots")') < downgrade_body.index(
        'op.drop_table("benchmark_cohorts")'
    )
