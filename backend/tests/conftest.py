import pytest
import sys
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, geo_score, activity_log, toolkit_files, report  # noqa: F401

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
