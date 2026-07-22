# backend/tests/test_win_loss_service.py
from datetime import datetime

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.content_brief import ContentBrief
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.win_loss_service import classify_result, compute_win_loss


def _seed_client(db, name="ACME Corp"):
    client = Client(name=name, website="https://acme.example", industry="Technology")
    db.add(client)
    db.commit()
    return client


def _seed_scan(db, client, completed_at=None):
    scan = Scan(client_id=client.id, status="completed",
                completed_at=completed_at or datetime(2026, 6, 1, 12, 0))
    db.add(scan)
    db.commit()
    return scan


def _seed_result(db, scan, *, category="recommendation", platform="gemini",
                 response_text="", brand_detected=False, hallucination_flagged=False,
                 competitor_id=None, query_text="Best tech in KL"):
    r = ScanQueryResult(
        scan_id=scan.id, platform=platform, competitor_id=competitor_id,
        category=category, query_text=query_text, response_text=response_text,
        brand_detected=brand_detected, hallucination_flagged=hallucination_flagged,
    )
    db.add(r)
    db.commit()
    return r


def test_classify_result_outcomes():
    assert classify_result(True, []) == "won"
    assert classify_result(True, ["RivalCo"]) == "shared"
    assert classify_result(False, ["RivalCo"]) == "lost"
    assert classify_result(False, []) == "open"


def test_compute_win_loss_classifies_entries(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    scan = _seed_scan(db, client)

    _seed_result(db, scan, response_text="RivalCo is the best choice.", brand_detected=False)  # lost
    _seed_result(db, scan, response_text="ACME Corp leads the market.", brand_detected=True)   # won
    _seed_result(db, scan, response_text="Both ACME Corp and RivalCo are good.", brand_detected=True)  # shared
    _seed_result(db, scan, response_text="Many options exist.", brand_detected=False)          # open

    result = compute_win_loss(client.id, db)

    assert result.scan_id == scan.id
    assert result.summary == {"won": 1, "lost": 1, "shared": 1, "open": 1}
    lost = [e for e in result.entries if e.outcome == "lost"][0]
    assert lost.competitors_seen == ["RivalCo"]
    assert lost.client_seen is False


def test_compute_win_loss_only_neutral_categories(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    scan = _seed_scan(db, client)

    _seed_result(db, scan, category="brand", response_text="RivalCo wins.", brand_detected=False)
    _seed_result(db, scan, category="comparison", response_text="RivalCo wins.", brand_detected=False)
    _seed_result(db, scan, category="local", response_text="RivalCo wins.", brand_detected=False)

    result = compute_win_loss(client.id, db)
    assert len(result.entries) == 1
    assert result.entries[0].category == "local"


def test_compute_win_loss_excludes_flagged_and_handles_null_response(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    scan = _seed_scan(db, client)

    _seed_result(db, scan, response_text="RivalCo.", brand_detected=False, hallucination_flagged=True)
    no_text = _seed_result(db, scan, response_text=None, brand_detected=False)

    result = compute_win_loss(client.id, db)
    assert len(result.entries) == 1
    assert result.entries[0].result_id == no_text.id
    assert result.entries[0].outcome == "open"  # None response → no competitor seen


def test_compute_win_loss_ignores_competitor_rows(db):
    client = _seed_client(db)
    comp = Competitor(client_id=client.id, name="RivalCo")
    db.add(comp)
    db.commit()
    scan = _seed_scan(db, client)
    _seed_result(db, scan, response_text="RivalCo.", brand_detected=True, competitor_id=comp.id)

    result = compute_win_loss(client.id, db)
    assert result.entries == []


def test_compute_win_loss_attaches_existing_brief(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    scan = _seed_scan(db, client)
    lost = _seed_result(db, scan, response_text="RivalCo only.", brand_detected=False)
    db.add(ContentBrief(
        client_id=client.id, scan_query_result_id=lost.id, platform=lost.platform,
        query_text=lost.query_text, competitors_seen=["RivalCo"],
        title="Win this query", angle="Be specific.", outline=["Intro", "Proof"],
    ))
    db.commit()

    result = compute_win_loss(client.id, db)
    assert result.entries[0].brief is not None
    assert result.entries[0].brief.title == "Win this query"


def test_compute_win_loss_without_scan_returns_empty(db):
    client = _seed_client(db)
    result = compute_win_loss(client.id, db)
    assert result.scan_id is None
    assert result.entries == []
    assert result.summary == {}


def test_compute_win_loss_uses_latest_completed_scan(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    old_scan = _seed_scan(db, client, completed_at=datetime(2026, 5, 1))
    new_scan = _seed_scan(db, client, completed_at=datetime(2026, 6, 1))
    _seed_result(db, old_scan, response_text="RivalCo.", brand_detected=False)
    _seed_result(db, new_scan, response_text="ACME Corp.", brand_detected=True)

    result = compute_win_loss(client.id, db)
    assert result.scan_id == new_scan.id
    assert result.summary == {"won": 1, "lost": 0, "shared": 0, "open": 0}
