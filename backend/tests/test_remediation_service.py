import uuid
from datetime import datetime, timedelta

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.competitor import Competitor
from app.models.remediation_item import RemediationItem
from app.services.remediation_service import (
    sync_remediation_items,
    get_remediation_items,
    set_remediation_status,
)


def _client(db) -> Client:
    c = Client(name="Acme Dental", website="acme.com", industry="dentist")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _completed_scan(db, client_id, when=None) -> Scan:
    s = Scan(client_id=client_id, status="completed", completed_at=when or datetime.utcnow())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_sync_creates_flagged_hallucination(db):
    client = _client(db)
    scan = _completed_scan(db, client.id)
    db.add(ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="brand",
        query_text="Is Acme open 24/7?", brand_detected=True,
        hallucination_flagged=True,
    ))
    db.commit()

    sync_remediation_items(client.id, db)

    items = get_remediation_items(client.id, db)
    hallucinations = [i for i in items if i.item_type == "hallucination"]
    assert len(hallucinations) == 1
    assert hallucinations[0].status == "flagged"
    assert hallucinations[0].label == "Is Acme open 24/7?"
    assert hallucinations[0].platform == "perplexity"


def test_sync_creates_content_gap_from_lost_query(db):
    client = _client(db)
    db.add(Competitor(client_id=client.id, name="BrightSmile", website="bright.com"))
    scan = _completed_scan(db, client.id)
    # Neutral-intent (recommendation) query the client lost: brand not detected,
    # but a competitor name appears in the stored response.
    db.add(ScanQueryResult(
        scan_id=scan.id, platform="chatgpt", category="recommendation",
        query_text="Best dentist in KL", brand_detected=False,
        response_text="The best options include BrightSmile and others.",
        hallucination_flagged=False,
    ))
    db.commit()

    sync_remediation_items(client.id, db)

    gaps = [i for i in get_remediation_items(client.id, db) if i.item_type == "content_gap"]
    assert len(gaps) == 1
    assert gaps[0].status == "flagged"
    assert gaps[0].label == "Best dentist in KL"
    assert "BrightSmile" in (gaps[0].detail or "")


def test_sync_auto_corrects_when_hallucination_gone(db):
    client = _client(db)
    # An existing flagged item from a prior scan.
    item = RemediationItem(
        client_id=client.id, item_type="hallucination", platform="perplexity",
        label="Is Acme open 24/7?", status="flagged",
    )
    db.add(item)
    # A new completed scan that no longer flags it (no flagged results at all).
    _completed_scan(db, client.id)
    db.commit()

    sync_remediation_items(client.id, db)

    refreshed = db.get(RemediationItem, item.id)
    assert refreshed.status == "corrected"
    assert refreshed.resolved_at is not None


def test_sync_reopens_corrected_item_if_problem_returns(db):
    client = _client(db)
    item = RemediationItem(
        client_id=client.id, item_type="hallucination", platform="perplexity",
        label="Is Acme open 24/7?", status="corrected", resolved_at=datetime.utcnow(),
    )
    db.add(item)
    scan = _completed_scan(db, client.id)
    db.add(ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="brand",
        query_text="Is Acme open 24/7?", brand_detected=True,
        hallucination_flagged=True,
    ))
    db.commit()

    sync_remediation_items(client.id, db)

    refreshed = db.get(RemediationItem, item.id)
    assert refreshed.status == "flagged"
    assert refreshed.resolved_at is None


def test_manual_in_progress_status_is_preserved_on_resync(db):
    client = _client(db)
    item = RemediationItem(
        client_id=client.id, item_type="hallucination", platform="perplexity",
        label="Is Acme open 24/7?", status="in_progress",
    )
    db.add(item)
    scan = _completed_scan(db, client.id)
    db.add(ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="brand",
        query_text="Is Acme open 24/7?", brand_detected=True,
        hallucination_flagged=True,
    ))
    db.commit()

    sync_remediation_items(client.id, db)

    # Still present in the scan, so an admin's "in_progress" must not be reset.
    assert db.get(RemediationItem, item.id).status == "in_progress"


def test_set_remediation_status_sets_and_clears_resolved_at(db):
    client = _client(db)
    item = RemediationItem(
        client_id=client.id, item_type="content_gap", platform="chatgpt",
        label="Best dentist in KL", status="flagged",
    )
    db.add(item)
    db.commit()

    set_remediation_status(item.id, "corrected", db)
    assert db.get(RemediationItem, item.id).resolved_at is not None

    set_remediation_status(item.id, "in_progress", db)
    assert db.get(RemediationItem, item.id).resolved_at is None


def test_get_items_orders_active_before_corrected(db):
    client = _client(db)
    db.add(RemediationItem(client_id=client.id, item_type="content_gap", platform="x",
                           label="corrected one", status="corrected", resolved_at=datetime.utcnow()))
    db.add(RemediationItem(client_id=client.id, item_type="content_gap", platform="y",
                           label="open one", status="flagged"))
    db.commit()

    items = get_remediation_items(client.id, db)
    assert items[0].status == "flagged"
    assert items[-1].status == "corrected"

    active_only = get_remediation_items(client.id, db, include_corrected=False)
    assert all(i.status != "corrected" for i in active_only)
