from datetime import datetime, timedelta

from app.core.constants import CHURN_DELETE_DAYS, RAW_RESPONSE_RETENTION_DAYS
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.retention_service import (
    delete_churned_clients,
    purge_raw_responses,
)


def _make_client(db, name="Acme Corp", **kwargs):
    c = Client(name=name, website="https://acme.com", industry="Technology", **kwargs)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_result(db, scan, response_text, created_at):
    r = ScanQueryResult(
        scan_id=scan.id,
        platform="chatgpt",
        category="brand",
        query_text="Tell me about Acme",
        response_text=response_text,
        brand_detected=True,
        created_at=created_at,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_scan(db, client):
    s = Scan(client_id=client.id, platform="multi", status="completed")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_purge_nulls_only_old_responses(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    now = datetime.utcnow()
    old = _make_result(db, scan, "old raw text", now - timedelta(days=RAW_RESPONSE_RETENTION_DAYS + 1))
    recent = _make_result(db, scan, "recent raw text", now - timedelta(days=1))

    purged = purge_raw_responses(db)

    db.refresh(old)
    db.refresh(recent)
    assert purged == 1
    assert old.response_text is None
    assert recent.response_text == "recent raw text"
    # Detection flag survives the purge — keeps competitor intel working.
    assert old.brand_detected is True


def test_purge_is_idempotent(db):
    client = _make_client(db)
    scan = _make_scan(db, client)
    _make_result(db, scan, "old", datetime.utcnow() - timedelta(days=RAW_RESPONSE_RETENTION_DAYS + 5))

    assert purge_raw_responses(db) == 1
    assert purge_raw_responses(db) == 0


def test_delete_removes_only_long_archived_clients(db):
    now = datetime.utcnow()
    churned = _make_client(db, name="Churned", archived_at=now - timedelta(days=CHURN_DELETE_DAYS + 1))
    recently_archived = _make_client(db, name="RecentlyArchived", archived_at=now - timedelta(days=1))
    active = _make_client(db, name="Active")

    deleted = delete_churned_clients(db)

    assert deleted == 1
    remaining = {c.name for c in db.query(Client).all()}
    assert remaining == {"RecentlyArchived", "Active"}
    assert db.get(Client, churned.id) is None
    assert db.get(Client, recently_archived.id) is not None
    assert db.get(Client, active.id) is not None


def test_delete_noop_when_nothing_churned(db):
    _make_client(db, name="Active")
    _make_client(db, name="RecentlyArchived", archived_at=datetime.utcnow() - timedelta(days=1))
    assert delete_churned_clients(db) == 0
