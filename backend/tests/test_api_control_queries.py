import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.constants import MAX_CONTROL_QUERIES
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


def _client(db):
    c = Client(name="Clinic A", website="https://a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    return c


def test_control_query_crud_roundtrip(db):
    app = _make_app(db)
    c = _client(db)
    http = TestClient(app)

    # create
    resp = http.post(
        f"/api/v1/clients/{c.id}/control-queries",
        json={"query_text": "Best physio in Penang", "category": "recommendation"},
    )
    assert resp.status_code == 201
    cq_id = resp.json()["id"]
    assert resp.json()["active"] is True

    # list
    resp = http.get(f"/api/v1/clients/{c.id}/control-queries")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # deactivate
    resp = http.patch(
        f"/api/v1/clients/{c.id}/control-queries/{cq_id}",
        json={"active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # reactivate
    resp = http.patch(
        f"/api/v1/clients/{c.id}/control-queries/{cq_id}",
        json={"active": True},
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    app.dependency_overrides.clear()


def test_control_query_cap_rejected(db):
    app = _make_app(db)
    c = _client(db)
    http = TestClient(app)
    for i in range(MAX_CONTROL_QUERIES):
        resp = http.post(
            f"/api/v1/clients/{c.id}/control-queries",
            json={"query_text": f"benchmark {i}", "category": "recommendation"},
        )
        assert resp.status_code == 201
    resp = http.post(
        f"/api/v1/clients/{c.id}/control-queries",
        json={"query_text": "one too many", "category": "recommendation"},
    )
    assert resp.status_code == 422
    assert "Maximum 5 benchmark queries" in resp.json()["detail"]
    app.dependency_overrides.clear()


def test_control_query_cap_counts_active_only(db):
    app = _make_app(db)
    c = _client(db)
    http = TestClient(app)
    ids = []
    for i in range(MAX_CONTROL_QUERIES):
        resp = http.post(
            f"/api/v1/clients/{c.id}/control-queries",
            json={"query_text": f"benchmark {i}", "category": "recommendation"},
        )
        ids.append(resp.json()["id"])
    http.patch(f"/api/v1/clients/{c.id}/control-queries/{ids[0]}", json={"active": False})
    resp = http.post(
        f"/api/v1/clients/{c.id}/control-queries",
        json={"query_text": "replacement", "category": "recommendation"},
    )
    assert resp.status_code == 201
    app.dependency_overrides.clear()


def test_control_query_foreign_client_404(db):
    app = _make_app(db)
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/control-queries")
    assert resp.status_code == 404
    app.dependency_overrides.clear()
