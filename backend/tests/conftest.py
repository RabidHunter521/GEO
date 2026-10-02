import pytest
import sys
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot, control_query, guarantee, site_audit, page_audit, content_deliverable, authority_asset, work_log_entry, misinformation_finding, outcome_action, business_location, truth_fact, tracked_query, conversion_event, attribution_setting, attribution_signal, search_query_signal, benchmark_cohort, benchmark_snapshot, benchmark_publication, workspace, user  # noqa: F401


# Other test modules import models with JSONB columns (content_analyses),
# which SQLite can't compile during create_all — render them as JSON in tests.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# SQLite gives a column declared "UUID" NUMERIC affinity, so a random uuid4
# whose hex is all digits plus one "e" (e.g. 12345678...789e12) is silently
# stored as a float and reads back as one -- a ~1-in-a-million-per-uuid flake
# that surfaced as "'float' object has no attribute 'replace'". CHAR(32) has
# TEXT affinity and stores the hex verbatim. Postgres has a real UUID type.
@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"

# Mock resend module if not installed
if "resend" not in sys.modules:
    sys.modules["resend"] = MagicMock()


@pytest.fixture
def db() -> Session:
    # StaticPool (not the sqlite-for-:memory: default SingletonThreadPool) so the
    # exact same physical connection is reused regardless of which thread checks
    # it out — FastAPI offloads sync routes/dependencies to a threadpool, and a
    # SingletonThreadPool hands a *different*, schema-less :memory: connection to
    # any thread that hasn't touched this engine before (bites right after a
    # commit(), which releases the connection back to the pool for the next
    # checkout). Needed by tests that call TestClient against a real `db` session
    # across a commit boundary (e.g. test_authority_api.py); harmless no-op for
    # tests that only ever use one connection already.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    # Every client belongs to a workspace (FK enforced above); production gets
    # this row from the b956747aed6c migration.
    import uuid as _uuid
    from app.core.constants import DEFAULT_WORKSPACE_ID, DEFAULT_WORKSPACE_NAME
    from app.models.workspace import Workspace

    session.add(Workspace(id=_uuid.UUID(DEFAULT_WORKSPACE_ID), name=DEFAULT_WORKSPACE_NAME))
    session.commit()
    # A signed-up owner so API tests can authenticate (tests/auth_helpers.py).
    from tests.auth_helpers import seed_test_owner

    seed_test_owner(session)
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
