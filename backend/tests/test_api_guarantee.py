import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan


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


def _client_with_score(db, citability=42.0):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c)
    db.commit()
    s = Scan(client_id=c.id, status="completed")
    db.add(s)
    db.commit()
    db.add(GeoScore(client_id=c.id, scan_id=s.id, ai_citability=citability,
                    brand_authority=0.0, content_quality=0.0,
                    technical_foundations=0.0, structured_data=0.0,
                    overall_score=citability))
    db.commit()
    return c


def _deadline():
    return (date.today() + timedelta(days=90)).isoformat()


def test_guarantee_crud_roundtrip(db):
    app = _make_app(db)
    c = _client_with_score(db)
    http = TestClient(app)

    # no guarantee yet
    resp = http.get(f"/api/v1/clients/{c.id}/guarantee")
    assert resp.status_code == 200
    assert resp.json() is None

    # create (baseline auto-filled)
    resp = http.post(
        f"/api/v1/clients/{c.id}/guarantee",
        json={"metric": "ai_citability", "target_value": 60, "deadline_date": _deadline()},
    )
    assert resp.status_code == 201, resp.text
    gid = resp.json()["id"]
    assert resp.json()["baseline_value"] == 42

    # progress payload
    resp = http.get(f"/api/v1/clients/{c.id}/guarantee")
    body = resp.json()
    assert body["state"] in ("on_track", "at_risk", "met")
    assert body["current_value"] == 42.0
    assert body["points_needed"] == 18

    # duplicate active → 422
    resp = http.post(
        f"/api/v1/clients/{c.id}/guarantee",
        json={"metric": "ai_citability", "target_value": 70, "deadline_date": _deadline()},
    )
    assert resp.status_code == 422

    # resolve
    resp = http.post(
        f"/api/v1/clients/{c.id}/guarantee/{gid}/resolve",
        json={"outcome": "void", "note": "client paused"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "void"

    # resolved → progress null again
    resp = http.get(f"/api/v1/clients/{c.id}/guarantee")
    assert resp.json() is None
    app.dependency_overrides.clear()


def test_guarantee_foreign_client_404(db):
    app = _make_app(db)
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/guarantee")
    assert resp.status_code == 404
    app.dependency_overrides.clear()


def test_resolve_wrong_client_404(db):
    app = _make_app(db)
    c = _client_with_score(db)
    other = _client_with_score(db)
    http = TestClient(app)
    resp = http.post(
        f"/api/v1/clients/{c.id}/guarantee",
        json={"metric": "ai_citability", "target_value": 60, "deadline_date": _deadline()},
    )
    gid = resp.json()["id"]
    resp = http.post(
        f"/api/v1/clients/{other.id}/guarantee/{gid}/resolve",
        json={"outcome": "met"},
    )
    assert resp.status_code == 404
    app.dependency_overrides.clear()
