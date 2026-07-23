import pytest
import sys
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot, control_query, guarantee, site_audit, page_audit, content_deliverable, authority_asset  # noqa: F401


# Other test modules import models with JSONB columns (content_analyses),
# which SQLite can't compile during create_all — render them as JSON in tests.
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

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
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
