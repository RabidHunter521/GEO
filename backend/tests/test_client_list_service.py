import uuid
from datetime import datetime, timedelta

from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.services.client_list_service import build_client_list


def _make_client(db, name="Acme Corp", **kwargs):
    c = Client(name=name, website="https://acme.com", industry="Technology", **kwargs)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_scan(db, client, status="completed", triggered_at=None):
    s = Scan(client_id=client.id, platform="multi", status=status)
    if triggered_at:
        s.triggered_at = triggered_at
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _make_score(db, client, scan, overall, computed_at, score_id=None):
    g = GeoScore(
        client_id=client.id,
        scan_id=scan.id,
        overall_score=overall,
        computed_at=computed_at,
    )
    if score_id:
        g.id = score_id
    db.add(g)
    db.commit()
    return g


def test_client_with_no_scans_has_null_enrichment(db):
    _make_client(db)
    items = build_client_list(db)
    assert len(items) == 1
    item = items[0]
    assert item.latest_overall_score is None
    assert item.previous_overall_score is None
    assert item.last_scan_at is None
    assert item.latest_scan_status is None
    assert item.latest_scan_triggered_at is None


def test_client_with_one_score_has_no_previous(db):
    c = _make_client(db)
    scan = _make_scan(db, c)
    _make_score(db, c, scan, 72.0, datetime(2026, 6, 1))
    items = build_client_list(db)
    item = items[0]
    assert item.latest_overall_score == 72.0
    assert item.previous_overall_score is None
    assert item.last_scan_at == datetime(2026, 6, 1)
    assert item.latest_scan_status == "completed"


def test_client_with_three_scores_picks_two_latest(db):
    c = _make_client(db)
    for overall, day in [(50.0, 1), (60.0, 5), (70.0, 10)]:
        scan = _make_scan(db, c, triggered_at=datetime(2026, 6, day))
        _make_score(db, c, scan, overall, datetime(2026, 6, day))
    items = build_client_list(db)
    item = items[0]
    assert item.latest_overall_score == 70.0
    assert item.previous_overall_score == 60.0
    assert item.last_scan_at == datetime(2026, 6, 10)


def test_failed_scan_without_score_surfaces_status(db):
    c = _make_client(db)
    _make_scan(db, c, status="failed", triggered_at=datetime(2026, 6, 1))
    items = build_client_list(db)
    item = items[0]
    assert item.latest_overall_score is None
    assert item.last_scan_at is None
    assert item.latest_scan_status == "failed"
    assert item.latest_scan_triggered_at == datetime(2026, 6, 1)


def test_latest_scan_status_reflects_most_recent_scan(db):
    c = _make_client(db)
    old = _make_scan(db, c, status="completed", triggered_at=datetime(2026, 6, 1))
    _make_score(db, c, old, 65.0, datetime(2026, 6, 1))
    _make_scan(db, c, status="running", triggered_at=datetime(2026, 6, 10))
    items = build_client_list(db)
    item = items[0]
    assert item.latest_scan_status == "running"
    assert item.latest_overall_score == 65.0  # score from the completed scan


def test_archived_clients_excluded(db):
    _make_client(db, name="Active")
    _make_client(db, name="Gone", archived_at=datetime(2026, 6, 1))
    items = build_client_list(db)
    assert [i.name for i in items] == ["Active"]


def test_computed_at_tie_broken_by_id(db):
    c = _make_client(db)
    same_time = datetime(2026, 6, 1, 12, 0, 0)
    scan = _make_scan(db, c, triggered_at=same_time)
    _make_score(db, c, scan, 40.0, same_time, score_id=uuid.UUID(int=1))
    _make_score(db, c, scan, 90.0, same_time, score_id=uuid.UUID(int=2))
    items = build_client_list(db)
    item = items[0]
    # higher id wins the tie as "latest" — deterministic either way
    assert item.latest_overall_score == 90.0
    assert item.previous_overall_score == 40.0


def test_enrichment_is_per_client(db):
    a = _make_client(db, name="A")
    b = _make_client(db, name="B")
    scan_a = _make_scan(db, a, triggered_at=datetime(2026, 6, 1))
    _make_score(db, a, scan_a, 55.0, datetime(2026, 6, 1))
    items = {i.name: i for i in build_client_list(db)}
    assert items["A"].latest_overall_score == 55.0
    assert items["B"].latest_overall_score is None
    assert items["B"].latest_scan_status is None
