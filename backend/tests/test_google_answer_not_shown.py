"""Google AI surfaces Task 4: a search with no AI Overview is never quoted,
fact-checked or read as a fix, but still counts as Not seen by AI."""
import uuid
from types import SimpleNamespace

from app.core.time import utcnow
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult, has_answer
from app.services import proof_card_service
from app.services.ai_mirror_service import build_ai_mirror
from app.services.misinformation_service import check_candidate_fixed, review_finding
from tests.test_ai_mirror import _client, _competitor, _row, _scan
from tests.test_misinformation_workflow import _setup


def _no_overview(db, scan, query_text, competitor=None):
    row = _row(db, scan, platform="google_aio", query_text=query_text, response_text="",
               brand_detected=False, competitor=competitor)
    row.answer_shown = False
    db.flush()
    return row


def test_has_answer_is_false_only_for_an_answer_not_shown():
    assert has_answer(SimpleNamespace(answer_shown=False)) is False
    assert has_answer(SimpleNamespace(answer_shown=True)) is True
    assert has_answer(SimpleNamespace(answer_shown=None)) is True
    assert has_answer(SimpleNamespace()) is True


def test_mirror_says_no_overview_instead_of_quoting_nothing(db):
    client = _client(db)
    rival = _competitor(db, client, "Smile Studio")
    scan = _scan(db, client)
    _no_overview(db, scan, "Tell me about Acme Dental")
    seen = _row(db, scan, platform="google_aio", query_text="Tell me about Smile Studio",
                response_text="Smile Studio is a dental clinic in Bangsar.", brand_detected=True,
                competitor=rival)
    seen.answer_shown = True
    db.flush()

    [platform] = build_ai_mirror(client, db).platforms
    assert platform.platform == "google_aio"
    assert platform.you.status == "no_overview"
    assert platform.you.excerpts == [] and platform.you.response_text is None
    assert platform.competitor.status == "seen"


def test_no_overview_never_becomes_a_proof_card():
    row = SimpleNamespace(answer_shown=False, brand_detected=False, category="recommendation",
                          response_text="", platform="google_aio", recommendation_position=None)
    assert proof_card_service.result_excerpt(row, "Acme", ["Smile Studio"]) == (None, None)
    assert proof_card_service.select_proof_cards([row], "Acme", ["Smile Studio"]) == []


def test_a_missing_overview_is_not_evidence_a_false_statement_was_fixed(db):
    client, _, result, finding = _setup(db)
    result.platform = "google_aio"
    result.answer_shown = True
    db.commit()
    review_finding(finding.id, "confirm", db)

    later = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(later)
    db.commit()
    db.add(ScanQueryResult(
        scan_id=later.id, platform="google_aio", category="brand",
        query_text=result.query_text, response_text="", brand_detected=False,
        answer_shown=False,
    ))
    db.commit()

    assert check_candidate_fixed(later.id, db) == 0
    db.refresh(finding)
    assert finding.status == "confirmed"


def test_share_view_scan_row_flags_no_overview_and_still_reads_not_seen(db):
    from fastapi.testclient import TestClient

    from app.main import app

    client = _client(db)
    scan = _scan(db, client)
    _no_overview(db, scan, "best dental clinic in KL")
    db.commit()

    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        body = TestClient(app).get(f"/api/v1/view/{client.share_token}/scan").json()
    finally:
        app.dependency_overrides.pop(get_db, None)

    [row] = body["results"]
    assert row["platform_label"] == "Google AI Overviews"
    assert row["seen_by_ai"] is False
    assert row["ai_answer_shown"] is False
    assert row["excerpt"] is None
    assert "response_text" not in row and "answer_shown" not in row


def test_admin_scan_rows_carry_answer_shown(db):
    from app.schemas.scan import ScanQueryResultResponse

    r = ScanQueryResultResponse(
        id=uuid.uuid4(), scan_id=uuid.uuid4(), platform="google_aio", category="local",
        query_text="q", brand_detected=False, answer_shown=False, created_at=utcnow(),
    )
    assert r.answer_shown is False
