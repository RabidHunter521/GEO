from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.base import Base
from app.models.client import Client


@pytest.fixture
def db():
    # StaticPool: TestClient serves requests from a worker thread; a plain
    # in-memory engine would hand that thread a fresh (empty) database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def _make_app(db):
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import require_api_key
    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return app


def _client(db, prop="123456789"):
    c = Client(name="A", website="https://a.my", industry="x", ga4_property_id=prop)
    db.add(c)
    db.commit()
    return c


ROWS = [("202607", "chatgpt.com", 140), ("202607", "perplexity.ai", 60)]


def test_sync_endpoint_returns_report(db):
    app = _make_app(db)
    c = _client(db)
    http = TestClient(app)
    with patch("app.services.ga4_traffic_service._fetch_rows", return_value=ROWS):
        resp = http.post(f"/api/v1/clients/{c.id}/traffic/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["synced_periods"] == ["2026-07-01"]
    assert body["skipped_manual"] == []
    assert body["error"] is None
    app.dependency_overrides.clear()


def test_sync_endpoint_error_is_200_with_error_field(db):
    app = _make_app(db)
    c = _client(db, prop=None)
    http = TestClient(app)
    resp = http.post(f"/api/v1/clients/{c.id}/traffic/sync")
    assert resp.status_code == 200
    assert resp.json()["error"] is not None
    app.dependency_overrides.clear()


def test_property_id_persists_via_client_update(db):
    app = _make_app(db)
    c = _client(db, prop=None)
    http = TestClient(app)
    resp = http.patch(f"/api/v1/clients/{c.id}", json={"ga4_property_id": "987654321"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["ga4_property_id"] == "987654321"
    app.dependency_overrides.clear()


def test_manual_upsert_reverts_source_to_manual(db):
    app = _make_app(db)
    c = _client(db)
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1), ai_visitors=200,
                             source="ga4", breakdown={"chatgpt.com": 200}))
    db.commit()
    http = TestClient(app)
    resp = http.put(
        f"/api/v1/clients/{c.id}/traffic",
        json={"period": "2026-07-01", "ai_visitors": 350},
    )
    assert resp.status_code == 200, resp.text
    snap = db.query(AiTrafficSnapshot).one()
    db.refresh(snap)
    assert snap.source == "manual"       # explicit admin action wins
    assert snap.breakdown is None        # stale ga4 split must not linger
    assert snap.ai_visitors == 350
    app.dependency_overrides.clear()
