"""Static checks for the Phase 5 Task 1 migration.

The migration uses JSONB-adjacent Postgres-only DDL (partial unique indexes,
ROW LEVEL SECURITY) and cannot run against the SQLite test database — see
test_migration_chain.py's module docstring for why the project's convention
is to verify structure statically here and run the real migration against
Postgres in CI / the release runbook instead of in this suite.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND / "alembic" / "versions" / "d1a7c5f4e0b2_add_measurement_and_business_proof.py"
)
REVISION_ID = "d1a7c5f4e0b2"
DOWN_REVISION_ID = "c0f6b4e3d9a1"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_migration_file_exists():
    assert MIGRATION_PATH.exists()


def test_migration_declares_expected_revision_ids():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert f'revision: str = "{REVISION_ID}"' in source
    assert f'down_revision: Union[str, None] = "{DOWN_REVISION_ID}"' in source


def test_migration_chains_from_phase_4_head():
    """The plan's pre-flight scan found alembic head == c0f6b4e3d9a1 with no
    drift; this migration must extend that exact chain. It is no longer the
    single chain head (Tasks 5+6 migrations and a merge migration extend it),
    but its parent must still be Phase 4's final head."""
    script = _script_dir()
    revision = script.get_revision(REVISION_ID)
    assert revision is not None
    assert revision.down_revision == DOWN_REVISION_ID

    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one chain head, found {heads}"


def test_migration_creates_tracked_queries_table_with_required_columns():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "tracked_queries"' in source

    required_columns = [
        '"id"',
        '"client_id"',
        '"location_id"',
        '"text"',
        '"normalized_text"',
        '"source"',
        '"intent"',
        '"buyer_stage"',
        '"service_key"',
        '"risk_level"',
        '"demand_weight"',
        '"priority_score"',
        '"is_active"',
        '"created_at"',
        '"updated_at"',
    ]
    for column in required_columns:
        assert column in source, f"tracked_queries is missing column {column}"


def test_migration_adds_sample_metadata_columns_to_scan_query_results():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    for column in (
        "tracked_query_id",
        "sample_index",
        "prompt_version",
        "model_name",
        "model_version",
        "observed_at",
    ):
        assert f'"{column}"' in source, f"scan_query_results migration is missing column {column}"
        assert "scan_query_results" in source


def test_migration_declares_partial_unique_indexes_as_raw_sql():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "uq_tracked_query_brand" in source
    assert "uq_tracked_query_location" in source
    assert "WHERE location_id IS NULL" in source
    assert "WHERE location_id IS NOT NULL" in source
    # Per the plan: partial unique indexes must be raw op.execute() SQL, not
    # a SQLAlchemy create_index() dialect kwarg, so the Postgres-only nature
    # of a partial index is explicit rather than hidden behind an argument.
    upgrade_body = source.split("def upgrade() -> None:")[1].split("def downgrade()")[0]
    assert "postgresql_where" not in upgrade_body


def test_migration_declares_documented_indexes():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    for index_name in (
        "ix_tracked_queries_client_active_priority",
        "ix_tracked_queries_client_location_intent",
        "ix_scan_query_results_tracked_query_observed",
        "ix_scan_query_results_scan_tracked_sample",
    ):
        assert index_name in source


def test_migration_enables_rls_and_revokes_anon_on_tracked_queries():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ALTER TABLE tracked_queries ENABLE ROW LEVEL SECURITY;" in source
    assert "REVOKE ALL ON TABLE tracked_queries FROM anon;" in source


def test_migration_grants_no_new_role_access():
    """RLS is enabled with zero policies (CLAUDE.md §8): only `postgres`
    (which bypasses RLS) connects, so this migration must not GRANT anything
    to any role — that would be the data-loss path d3f7a1c58e02 closed."""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "GRANT " not in source.upper()


def test_migration_defines_symmetric_upgrade_and_downgrade():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
    # Every table/column created in upgrade must be dropped in downgrade.
    downgrade_body = source.split("def downgrade() -> None:")[1]
    assert 'op.drop_table("tracked_queries")' in downgrade_body
    for column in (
        "tracked_query_id",
        "sample_index",
        "prompt_version",
        "model_name",
        "model_version",
        "observed_at",
    ):
        assert f'op.drop_column("scan_query_results", "{column}")' in downgrade_body


def test_migration_has_non_negative_weight_check_constraints():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ck_tracked_queries_demand_weight_non_negative" in source
    assert "ck_tracked_queries_priority_score_non_negative" in source
    assert "demand_weight >= 0" in source
    assert "priority_score >= 0" in source


def test_migration_has_positive_sample_index_check_constraint():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "ck_scan_query_results_sample_index_positive" in source
    assert "sample_index > 0" in source
