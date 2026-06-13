import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.content_roadmap_service import generate_roadmap


def _seed_client(db, name="ACME Corp"):
    client = Client(name=name, website="https://acme.example", industry="Technology")
    db.add(client)
    db.commit()
    return client


def _seed_scan(db, client):
    scan = Scan(client_id=client.id, status="completed", completed_at=datetime(2026, 6, 1, 12, 0))
    db.add(scan)
    db.commit()
    return scan


def _seed_result(db, scan, *, category="recommendation", platform="gemini",
                 response_text="", brand_detected=False, query_text="Best tech in KL"):
    r = ScanQueryResult(
        scan_id=scan.id, platform=platform, competitor_id=None,
        category=category, query_text=query_text, response_text=response_text,
        brand_detected=brand_detected, hallucination_flagged=False,
    )
    db.add(r)
    db.commit()
    return r


def _fake_claude(payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_generate_roadmap_empty_when_no_lost_queries(db):
    client = _seed_client(db)
    scan = _seed_scan(db, client)
    # client is seen → "won", not lost/open
    _seed_result(db, scan, response_text="ACME Corp leads.", brand_detected=True)

    with patch("app.services.content_roadmap_service.anthropic_client") as mock_client:
        result = generate_roadmap(client, db)

    mock_client.assert_not_called()
    assert result == {"roadmap_json": [], "source_query_count": 0}


def test_generate_roadmap_builds_items_from_lost_queries(db):
    client = _seed_client(db)
    db.add(Competitor(client_id=client.id, name="RivalCo"))
    db.commit()
    scan = _seed_scan(db, client)
    _seed_result(db, scan, response_text="RivalCo is the best.", brand_detected=False,
                 query_text="Best tech company in KL")  # lost
    _seed_result(db, scan, response_text="Many options.", brand_detected=False,
                 query_text="Top tech firms")  # open

    claude_payload = {"roadmap": [{
        "month": 1, "theme": "Local authority", "priority": "high",
        "target_queries": ["Best tech company in KL"], "competitors_winning": ["RivalCo"],
        "content_type": "Blog post", "suggested_title": "Why ACME Corp Leads Tech in KL",
        "rationale": "Targets the exact lost query.",
    }]}

    with patch("app.services.content_roadmap_service.anthropic_client",
               return_value=_fake_claude(claude_payload)):
        result = generate_roadmap(client, db)

    assert result["source_query_count"] == 2
    assert len(result["roadmap_json"]) == 1
    item = result["roadmap_json"][0]
    assert item["month"] == 1
    assert item["priority"] == "high"
    assert item["suggested_title"] == "Why ACME Corp Leads Tech in KL"
    assert item["competitors_winning"] == ["RivalCo"]


def test_generate_roadmap_accepts_bare_list_payload(db):
    client = _seed_client(db)
    scan = _seed_scan(db, client)
    _seed_result(db, scan, response_text="Many options.", brand_detected=False)  # open

    bare = [{
        "month": 2, "theme": "FAQ", "priority": "medium",
        "target_queries": [], "competitors_winning": [],
        "content_type": "FAQ page", "suggested_title": "Tech FAQ", "rationale": "Covers gaps.",
    }]
    with patch("app.services.content_roadmap_service.anthropic_client",
               return_value=_fake_claude(bare)):
        result = generate_roadmap(client, db)

    assert len(result["roadmap_json"]) == 1
    assert result["roadmap_json"][0]["content_type"] == "FAQ page"


def test_generate_roadmap_skips_items_missing_title_or_theme(db):
    client = _seed_client(db)
    scan = _seed_scan(db, client)
    _seed_result(db, scan, response_text="Many options.", brand_detected=False)  # open

    payload = {"roadmap": [
        {"month": 1, "theme": "", "priority": "high", "suggested_title": "Has title but no theme"},
        {"month": 1, "theme": "Valid", "priority": "low", "suggested_title": "Valid Title",
         "content_type": "Blog post", "rationale": "ok"},
    ]}
    with patch("app.services.content_roadmap_service.anthropic_client",
               return_value=_fake_claude(payload)):
        result = generate_roadmap(client, db)

    assert len(result["roadmap_json"]) == 1
    assert result["roadmap_json"][0]["theme"] == "Valid"


def test_generate_roadmap_raises_when_no_valid_items(db):
    client = _seed_client(db)
    scan = _seed_scan(db, client)
    _seed_result(db, scan, response_text="Many options.", brand_detected=False)  # open

    payload = {"roadmap": [{"month": 1, "theme": "", "suggested_title": ""}]}
    with patch("app.services.content_roadmap_service.anthropic_client",
               return_value=_fake_claude(payload)):
        try:
            generate_roadmap(client, db)
            raised = False
        except ValueError:
            raised = True
    assert raised
