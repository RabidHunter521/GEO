import pytest
import sys
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker, Session
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log  # noqa: F401


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
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
