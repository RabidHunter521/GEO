"""POST /clients/{id}/reports/generate — worker-availability gate.

The route used to enqueue unconditionally and return {"status": "queued"}. With
the Celery worker down the job sat in Redis forever while the admin UI promised
an auto-update, then showed "No reports yet" — the failure a prospect saw during
the founder walkthrough (docs/demo/walkthrough.md §6.1 bug 6).

Fixtures mirror test_work_log_api.py.
"""
from unittest.mock import patch

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


def test_generate_enqueues_when_a_worker_is_online(client, db, auth_headers):
    c = _make_client(db)
    with patch("app.api.v1.reports.workers_online", return_value=True), \
            patch("workers.tasks.report_tasks.generate_client_report.delay") as delay:
        delay.return_value.id = "task-123"
        r = client.post(f"/api/v1/clients/{c.id}/reports/generate", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    delay.assert_called_once()


def test_generate_returns_503_when_no_worker_is_listening(client, db, auth_headers):
    c = _make_client(db)
    with patch("app.api.v1.reports.workers_online", return_value=False), \
            patch("workers.tasks.report_tasks.generate_client_report.delay") as delay:
        r = client.post(f"/api/v1/clients/{c.id}/reports/generate", headers=auth_headers)
    assert r.status_code == 503
    # The admin must be told what to do, not just that something failed.
    assert "worker" in r.json()["detail"].lower()
    # Nothing may be queued — a job nobody consumes is worse than a clear error.
    delay.assert_not_called()


def test_generate_returns_503_when_the_broker_is_unreachable(client, db, auth_headers):
    """ping() succeeding but delay() failing still must not read as success."""
    c = _make_client(db)
    with patch("app.api.v1.reports.workers_online", return_value=True), \
            patch("workers.tasks.report_tasks.generate_client_report.delay",
                  side_effect=OSError("connection refused")):
        r = client.post(f"/api/v1/clients/{c.id}/reports/generate", headers=auth_headers)
    assert r.status_code == 503
    assert "queue" in r.json()["detail"].lower()


def test_workers_online_is_false_when_ping_returns_nothing():
    from app.services.worker_health import workers_online
    with patch("app.services.worker_health.celery_app") as app_mock:
        app_mock.control.ping.return_value = []
        assert workers_online() is False


def test_workers_online_is_false_when_ping_raises():
    """A broker that refuses the connection must read as "no workers", not 500."""
    from app.services.worker_health import workers_online
    with patch("app.services.worker_health.celery_app") as app_mock:
        app_mock.control.ping.side_effect = OSError("connection refused")
        assert workers_online() is False


def test_workers_online_is_true_when_a_worker_replies():
    from app.services.worker_health import workers_online
    with patch("app.services.worker_health.celery_app") as app_mock:
        app_mock.control.ping.return_value = [{"celery@host": {"ok": "pong"}}]
        assert workers_online() is True
