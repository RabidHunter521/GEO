import json
from unittest.mock import patch

from app.core.time import utcnow
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.misinformation_service import detect

RESPONSE = "Klinik A offers laser eye surgery and guarantees full recovery for everyone."


def _client(db) -> Client:
    c = Client(name="Klinik A", website="klinik-a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _scan(db, client_id) -> Scan:
    s = Scan(client_id=client_id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _result(db, scan_id, **kw) -> ScanQueryResult:
    defaults = dict(
        platform="chatgpt", category="brand", query_text="Tell me about Klinik A",
        response_text=RESPONSE, brand_detected=True, hallucination_flagged=False,
    )
    defaults.update(kw)
    r = ScanQueryResult(scan_id=scan_id, **defaults)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _candidates(*quotes: str) -> str:
    return json.dumps([
        {"quote": q, "category": "prohibited_claim", "rule_key": "guaranteed_results",
         "severity": "high", "explanation": "Outcome guarantee the clinic cannot make."}
        for q in quotes
    ])


def test_verbatim_candidate_is_stored_as_suggested(db):
    client = _client(db)
    scan = _scan(db, client.id)
    _result(db, scan.id, hallucination_flagged=True)

    with patch("app.services.misinformation_service._call_claude",
               return_value=_candidates("guarantees full recovery")):
        stored = detect(scan.id, db)

    assert stored == 1
    row = db.query(MisinformationFinding).one()
    assert row.status == "suggested"
    assert row.quote == "guarantees full recovery"
    assert row.client_id == client.id


def test_fabricated_quote_is_rejected(db):
    """The firewall: Claude proposes a quote that is not in the response."""
    client = _client(db)
    scan = _scan(db, client.id)
    _result(db, scan.id, hallucination_flagged=True)

    with patch("app.services.misinformation_service._call_claude",
               return_value=_candidates("guarantees your money back")):
        stored = detect(scan.id, db)

    assert stored == 0
    assert db.query(MisinformationFinding).count() == 0


def test_quote_must_match_its_own_source_row(db):
    """A quote verbatim in ANOTHER row does not license a finding on this one."""
    client = _client(db)
    scan = _scan(db, client.id)
    _result(db, scan.id, platform="chatgpt", response_text="Klinik A is a dental clinic.",
            hallucination_flagged=True)

    with patch("app.services.misinformation_service._call_claude",
               return_value=_candidates("guarantees full recovery")):
        assert detect(scan.id, db) == 0


def test_duplicate_quote_skipped_against_open_finding(db):
    client = _client(db)
    scan = _scan(db, client.id)
    result = _result(db, scan.id, hallucination_flagged=True)
    db.add(MisinformationFinding(
        client_id=client.id, scan_query_result_id=result.id,
        quote="guarantees   full recovery", category="prohibited_claim",
        rule_key="guaranteed_results", severity="high", explanation="e",
        status="confirmed",
    ))
    db.commit()

    with patch("app.services.misinformation_service._call_claude",
               return_value=_candidates("guarantees full recovery")):
        assert detect(scan.id, db) == 0
    assert db.query(MisinformationFinding).count() == 1


def test_duplicate_quote_reopens_after_verified_fixed(db):
    """A statement we already fixed coming back is a regression worth flagging."""
    client = _client(db)
    scan = _scan(db, client.id)
    result = _result(db, scan.id, hallucination_flagged=True)
    db.add(MisinformationFinding(
        client_id=client.id, scan_query_result_id=result.id,
        quote="guarantees full recovery", category="prohibited_claim",
        rule_key="guaranteed_results", severity="high", explanation="e",
        status="verified_fixed",
    ))
    db.commit()

    with patch("app.services.misinformation_service._call_claude",
               return_value=_candidates("guarantees full recovery")):
        assert detect(scan.id, db) == 1
    assert db.query(MisinformationFinding).count() == 2


def test_claude_failure_never_raises(db):
    client = _client(db)
    scan = _scan(db, client.id)
    _result(db, scan.id, hallucination_flagged=True)

    with patch("app.services.misinformation_service._call_claude",
               side_effect=RuntimeError("API down")):
        assert detect(scan.id, db) == 0
    assert db.query(MisinformationFinding).count() == 0


def test_only_client_owned_relevant_rows_are_examined(db):
    client = _client(db)
    comp = Competitor(client_id=client.id, name="Rival Dental")
    db.add(comp)
    db.commit()
    scan = _scan(db, client.id)
    # Examined: brand_detected client row.
    _result(db, scan.id, platform="chatgpt", brand_detected=True)
    # Not examined: competitor row, control row, and a row with neither signal.
    _result(db, scan.id, platform="gemini", competitor_id=comp.id, brand_detected=True)
    _result(db, scan.id, platform="perplexity", brand_detected=True, is_control=True)
    _result(db, scan.id, platform="claude", brand_detected=False, hallucination_flagged=False)

    with patch("app.services.misinformation_service._call_claude", return_value="[]") as call:
        detect(scan.id, db)

    assert call.call_count == 1
    assert call.call_args[0][1].platform == "chatgpt"


def test_rows_without_response_text_are_skipped(db):
    """Purged responses (90-day retention) can't be quoted from."""
    client = _client(db)
    scan = _scan(db, client.id)
    _result(db, scan.id, response_text=None, hallucination_flagged=True)

    with patch("app.services.misinformation_service._call_claude", return_value="[]") as call:
        detect(scan.id, db)

    assert call.call_count == 0


def test_fan_out_is_capped_flagged_rows_first(db):
    client = _client(db)
    scan = _scan(db, client.id)
    for i in range(3):
        _result(db, scan.id, platform=f"brand{i}", brand_detected=True)
    _result(db, scan.id, platform="flagged", hallucination_flagged=True, brand_detected=False)

    with patch("app.services.misinformation_service.MISINFORMATION_MAX_ROWS_PER_SCAN", 2), \
            patch("app.services.misinformation_service._call_claude", return_value="[]") as call:
        detect(scan.id, db)

    assert call.call_count == 2
    # The admin-flagged row is never the one dropped by the cap.
    assert "flagged" in [c[0][1].platform for c in call.call_args_list]


def test_missing_scan_returns_zero(db):
    import uuid
    assert detect(uuid.uuid4(), db) == 0
