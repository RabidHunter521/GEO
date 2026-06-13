# backend/tests/test_content_brief_service.py
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models.client import Client
from app.models.content_brief import ContentBrief
from app.models.activity_log import ActivityLog
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.content_brief_service import generate_brief_for_result

_VALID_PAYLOAD = {
    "title": "Best Tech Consultancies in Kuala Lumpur",
    "angle": "Local proof beats generic claims.",
    "outline": ["Why KL businesses need this", "Our results", "FAQ"],
}


def _seed(db):
    client = Client(name="ACME Corp", website="https://acme.example", industry="Technology")
    db.add(client)
    db.commit()
    scan = Scan(client_id=client.id, status="completed", completed_at=datetime(2026, 6, 1))
    db.add(scan)
    db.commit()
    result = ScanQueryResult(
        scan_id=scan.id, platform="gemini", category="recommendation",
        query_text="Best tech in KL", response_text="RivalCo is great.",
        brand_detected=False,
    )
    db.add(result)
    db.commit()
    return client, result


def _mock_claude(text):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def test_valid_json_persists_brief(db):
    client, result = _seed(db)
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude(json.dumps(_VALID_PAYLOAD))):
        brief = generate_brief_for_result(client, result, ["RivalCo"], db)

    assert brief is not None
    stored = db.query(ContentBrief).all()
    assert len(stored) == 1
    assert stored[0].title == _VALID_PAYLOAD["title"]
    assert stored[0].outline == _VALID_PAYLOAD["outline"]
    assert stored[0].competitors_seen == ["RivalCo"]
    logs = db.query(ActivityLog).filter(ActivityLog.event_type == "brief_generated").all()
    assert len(logs) == 1


def test_fenced_json_is_handled(db):
    client, result = _seed(db)
    fenced = f"```json\n{json.dumps(_VALID_PAYLOAD)}\n```"
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude(fenced)):
        brief = generate_brief_for_result(client, result, ["RivalCo"], db)
    assert brief is not None
    assert brief.title == _VALID_PAYLOAD["title"]


def test_malformed_json_returns_none_and_persists_nothing(db):
    client, result = _seed(db)
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude("Sorry, I cannot help with that.")):
        brief = generate_brief_for_result(client, result, ["RivalCo"], db)
    assert brief is None
    assert db.query(ContentBrief).count() == 0
    assert db.query(ActivityLog).count() == 0


def test_missing_fields_returns_none(db):
    client, result = _seed(db)
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude(json.dumps({"title": "", "angle": "x", "outline": []}))):
        brief = generate_brief_for_result(client, result, [], db)
    assert brief is None
    assert db.query(ContentBrief).count() == 0


def test_regeneration_upserts_single_row(db):
    client, result = _seed(db)
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude(json.dumps(_VALID_PAYLOAD))):
        first = generate_brief_for_result(client, result, ["RivalCo"], db)
    first_generated_at = first.generated_at

    updated = dict(_VALID_PAYLOAD, title="Updated title")
    with patch("app.services.content_brief_service.anthropic_client",
               return_value=_mock_claude(json.dumps(updated))):
        second = generate_brief_for_result(client, result, ["RivalCo", "OtherCo"], db)

    assert db.query(ContentBrief).count() == 1
    assert second.id == first.id
    assert second.title == "Updated title"
    assert second.competitors_seen == ["RivalCo", "OtherCo"]
    assert second.generated_at >= first_generated_at
