"""Cross-client work-log queue (spec §3.1, §6). Mirrors test_work_log_api.py's
fixtures — conftest.py provides only `db` (a real in-memory SQLite session).
"""
from datetime import date, timedelta

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


def _make_client(db, name="Acme Dental", archived=False):
    from app.core.time import utcnow
    from app.models.client import Client
    c = Client(name=name, website=f"https://{name.replace(' ', '').lower()}.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    if archived:
        c.archived_at = utcnow()
    db.add(c)
    db.commit()
    return c


def test_suggested_across_clients_spans_clients_and_carries_client(db):
    from app.services import work_log_service
    a = _make_client(db, "Acme Dental")
    b = _make_client(db, "Bravo Legal")
    work_log_service.suggest(a.id, "technical", "Acme thing", "r:a", db)
    work_log_service.suggest(b.id, "content", "Bravo thing", "r:b", db)

    rows = work_log_service.suggested_across_clients(db)
    assert len(rows) == 2
    pairs = {(c.name, e.description) for e, c in rows}
    assert pairs == {("Acme Dental", "Acme thing"), ("Bravo Legal", "Bravo thing")}


def test_suggested_excludes_published_and_dismissed(db):
    from app.services import work_log_service
    c = _make_client(db)
    keep = work_log_service.suggest(c.id, "technical", "Still pending", "r:1", db)
    pub = work_log_service.suggest(c.id, "content", "Published", "r:2", db)
    work_log_service.update_entry(pub, {"status": "published"}, db)
    dis = work_log_service.suggest(c.id, "content", "Dismissed", "r:3", db)
    work_log_service.update_entry(dis, {"status": "dismissed"}, db)

    rows = work_log_service.suggested_across_clients(db)
    assert [e.id for e, _ in rows] == [keep.id]


def test_suggested_excludes_archived_clients(db):
    from app.services import work_log_service
    live = _make_client(db, "Live Client")
    gone = _make_client(db, "Archived Client", archived=True)
    work_log_service.suggest(live.id, "technical", "Visible", "r:1", db)
    work_log_service.suggest(gone.id, "technical", "Hidden", "r:2", db)

    rows = work_log_service.suggested_across_clients(db)
    assert [e.description for e, _ in rows] == ["Visible"]
    assert work_log_service.suggested_count(db) == 1


def test_suggested_count_matches_list_length(db):
    from app.services import work_log_service
    a = _make_client(db, "Acme Dental")
    b = _make_client(db, "Bravo Legal")
    for i in range(3):
        work_log_service.suggest(a.id, "technical", f"A{i}", f"r:a{i}", db)
    work_log_service.suggest(b.id, "content", "B0", "r:b0", db)

    assert work_log_service.suggested_count(db) == len(
        work_log_service.suggested_across_clients(db)) == 4


def test_suggested_grouped_by_client_then_newest_first(db):
    from app.services import work_log_service
    today = date.today()
    b = _make_client(db, "Bravo Legal")
    a = _make_client(db, "Acme Dental")
    # Intentionally inverted: Bravo has the newest entry_date, but Acme must come
    # first alphabetically. This ensures the test catches if Client.name is dropped
    # from the sort order. A pure entry_date DESC sort would return Bravo first.
    work_log_service.suggest(b.id, "content", "B newest", "r:b1", db, entry_date=today)
    work_log_service.suggest(a.id, "technical", "A newer", "r:a1", db,
                             entry_date=today - timedelta(days=2))
    work_log_service.suggest(a.id, "technical", "A older", "r:a2", db,
                             entry_date=today - timedelta(days=5))

    rows = work_log_service.suggested_across_clients(db)
    # Client name ascending, then newest entry_date first inside each client.
    assert [(c.name, e.description) for e, c in rows] == [
        ("Acme Dental", "A newer"),
        ("Acme Dental", "A older"),
        ("Bravo Legal", "B newest"),
    ]


def test_route_returns_suggestions_with_client_identity(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db, "Acme Dental")
    work_log_service.suggest(c.id, "technical", "Verified llms.txt", "r:1", db)

    r = client.get("/api/v1/work-log/suggested", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["client_id"] == str(c.id)
    assert body[0]["client_name"] == "Acme Dental"
    assert body[0]["category_label"] == "Technical"
    assert body[0]["description"] == "Verified llms.txt"
    assert body[0]["status"] == "suggested"


def test_route_excludes_non_suggested(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    pub = work_log_service.suggest(c.id, "content", "Published", "r:2", db)
    work_log_service.update_entry(pub, {"status": "published"}, db)

    r = client.get("/api/v1/work-log/suggested", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_count_route(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    work_log_service.suggest(c.id, "technical", "One", "r:1", db)
    work_log_service.suggest(c.id, "content", "Two", "r:2", db)

    r = client.get("/api/v1/work-log/suggested/count", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"count": 2}


def test_routes_require_auth(client, db):
    assert client.get("/api/v1/work-log/suggested").status_code == 401
    assert client.get("/api/v1/work-log/suggested/count").status_code == 401


def test_category_label_matches_between_client_and_global_routes(client, db, auth_headers):
    """Regression test: category_label used to be computed independently in
    work_log.py and work_log_global.py. Both routers now delegate to
    work_log_service.category_label(), so the same entry must render the same
    label whether fetched per-client or across all clients."""
    from app.services import work_log_service

    c = _make_client(db, "Acme Dental")
    entry = work_log_service.suggest(c.id, "authority", "Verified listing", "r:1", db)

    per_client = client.get(f"/api/v1/clients/{c.id}/work-log", headers=auth_headers)
    assert per_client.status_code == 200
    per_client_label = next(
        e["category_label"] for e in per_client.json() if e["id"] == str(entry.id)
    )

    global_resp = client.get("/api/v1/work-log/suggested", headers=auth_headers)
    assert global_resp.status_code == 200
    global_label = next(
        e["category_label"] for e in global_resp.json() if e["client_id"] == str(c.id)
    )

    assert per_client_label == global_label == "Authority"
