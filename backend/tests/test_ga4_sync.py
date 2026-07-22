from datetime import date
from unittest.mock import patch

from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client
from app.services.ga4_traffic_service import Ga4SyncError, sync_client_traffic


def _client(db, prop="123456789"):
    c = Client(name="A", website="https://a.my", industry="x", ga4_property_id=prop)
    db.add(c)
    db.commit()
    return c


ROWS = [("202607", "chatgpt.com", 140), ("202607", "perplexity.ai", 60)]


def test_sync_creates_ga4_snapshot(db):
    c = _client(db)
    with patch("app.services.ga4_traffic_service._fetch_rows", return_value=ROWS):
        report = sync_client_traffic(c.id, db)
    snap = db.query(AiTrafficSnapshot).one()
    assert (snap.ai_visitors, snap.source) == (200, "ga4")
    assert snap.breakdown == {"chatgpt.com": 140, "perplexity.ai": 60}
    assert report.synced_periods == [date(2026, 7, 1)]


def test_sync_updates_existing_ga4_row_but_skips_manual(db):
    c = _client(db)
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1),
                             ai_visitors=5, source="manual"))
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 6, 1),
                             ai_visitors=5, source="ga4"))
    db.commit()
    rows = ROWS + [("202606", "claude.ai", 33)]
    with patch("app.services.ga4_traffic_service._fetch_rows", return_value=rows):
        report = sync_client_traffic(c.id, db)
    july = db.query(AiTrafficSnapshot).filter_by(period=date(2026, 7, 1)).one()
    june = db.query(AiTrafficSnapshot).filter_by(period=date(2026, 6, 1)).one()
    assert (july.ai_visitors, july.source) == (5, "manual")   # untouched
    assert (june.ai_visitors, june.source) == (33, "ga4")     # updated
    assert report.skipped_manual == [date(2026, 7, 1)]


def test_sync_without_property_id_reports_error(db):
    c = _client(db, prop=None)
    report = sync_client_traffic(c.id, db)
    assert report.error is not None


def test_fetch_failure_reports_error_and_writes_nothing(db):
    c = _client(db)
    with patch("app.services.ga4_traffic_service._fetch_rows", side_effect=Ga4SyncError("quota")):
        report = sync_client_traffic(c.id, db)
    assert report.error == "quota"
    assert db.query(AiTrafficSnapshot).count() == 0
