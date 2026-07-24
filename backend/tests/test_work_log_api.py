"""work-log admin API (spec §3.4). Mirrors test_authority_api.py's fixtures —
local `client`/`auth_headers` fixtures (this codebase's conftest.py only
provides `db` — a real in-memory SQLite session). `client` wires that real
session into a TestClient via get_db override; `auth_headers` uses the real
ADMIN_API_KEY so test_requires_auth exercises real auth enforcement rather
than a bypassed dependency.
"""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings
    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_list_empty(client, db, auth_headers):
    c = _make_client(db)
    r = client.get(f"/api/v1/clients/{c.id}/work-log", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_manual_entry_is_published(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(
        f"/api/v1/clients/{c.id}/work-log", headers=auth_headers,
        json={"category": "authority", "description": "Submitted to three directories",
              "entry_date": "2026-07-24"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "published"
    assert body["source"] == "manual"


def test_publish_and_dismiss_transitions(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    entry = work_log_service.suggest(c.id, "technical", "Verified llms.txt", "ref:api", db)
    r = client.patch(f"/api/v1/clients/{c.id}/work-log/{entry.id}", headers=auth_headers,
                     json={"status": "published", "description": "Edited wording"})
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["description"] == "Edited wording"
    r2 = client.patch(f"/api/v1/clients/{c.id}/work-log/{entry.id}", headers=auth_headers,
                      json={"status": "dismissed"})
    assert r2.json()["status"] == "dismissed"


def test_status_filter(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    work_log_service.suggest(c.id, "technical", "S", "ref:s", db)
    work_log_service.create_manual(c.id, "content", "P", date(2026, 7, 24), db)
    suggested = client.get(f"/api/v1/clients/{c.id}/work-log?status=suggested",
                           headers=auth_headers).json()
    assert len(suggested) == 1 and suggested[0]["description"] == "S"


def test_unknown_category_rejected(client, db, auth_headers):
    c = _make_client(db)
    r = client.post(f"/api/v1/clients/{c.id}/work-log", headers=auth_headers,
                    json={"category": "bogus", "description": "x", "entry_date": "2026-07-24"})
    assert r.status_code == 422


def test_requires_auth(client, db):
    c = _make_client(db)
    assert client.get(f"/api/v1/clients/{c.id}/work-log").status_code in (401, 403)


def test_patch_unknown_entry_404s(client, db, auth_headers):
    c = _make_client(db)
    r = client.patch(f"/api/v1/clients/{c.id}/work-log/{uuid.uuid4()}",
                     headers=auth_headers, json={"status": "published"})
    assert r.status_code == 404
