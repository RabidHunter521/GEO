"""Client-facing surfaces for compliance findings: the monthly PDF section and
the weekly digest protection line. The invariant under test everywhere is that
only confirmed+ findings are ever rendered."""
from datetime import timedelta

from app.core.time import utcnow
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.report_service import (
    MisinformationSummary,
    ReportData,
    _build_misinformation_html,
    _gather_misinformation,
)

RESPONSE = "Klinik A guarantees full recovery and is located in Ipoh."


def _client(db) -> Client:
    c = Client(name="Klinik A", website="klinik-a.my", industry="dental clinic")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _finding(db, client, status, quote="guarantees full recovery", **kw):
    s = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    r = ScanQueryResult(
        scan_id=s.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?", response_text=RESPONSE, brand_detected=True,
    )
    db.add(r)
    db.commit()
    f = MisinformationFinding(
        client_id=client.id, scan_query_result_id=r.id, quote=quote,
        category="prohibited_claim", rule_key="guaranteed_results", severity="high",
        explanation="Outcome guarantee the clinic cannot make.", status=status, **kw,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def _data(summary: MisinformationSummary | None) -> ReportData:
    data = ReportData.__new__(ReportData)
    data.misinformation = summary
    return data


def test_no_section_without_confirmed_findings(db):
    client = _client(db)
    since = utcnow() - timedelta(days=30)
    assert _gather_misinformation(client, db, since) is None

    _finding(db, client, "suggested")
    _finding(db, client, "dismissed", quote="located in Ipoh")
    assert _gather_misinformation(client, db, since) is None
    assert _build_misinformation_html(_data(None)) == ""


def test_open_findings_are_counted_without_quoting_them(db):
    client = _client(db)
    _finding(db, client, "confirmed")
    summary = _gather_misinformation(client, db, utcnow() - timedelta(days=30))

    assert summary is not None
    assert summary.open_count == 1
    assert summary.fixed_stories == []
    html_out = _build_misinformation_html(_data(summary))
    assert "How AI Represents You" in html_out
    # An open (not yet corrected) finding is a work-in-progress, not a story to
    # tell — the client sees the count, not the damaging quote.
    assert "guarantees full recovery" not in html_out


def test_verified_fixed_renders_the_before_after_story(db):
    client = _client(db)
    _finding(db, client, "verified_fixed", resolved_at=utcnow())
    summary = _gather_misinformation(client, db, utcnow() - timedelta(days=30))

    assert summary is not None and summary.fixed_count == 1
    html_out = _build_misinformation_html(_data(summary))
    assert "AI previously said" in html_out
    assert "guarantees full recovery" in html_out
    assert "now corrected" in html_out


def test_fixes_outside_the_period_are_not_reprinted(db):
    client = _client(db)
    _finding(db, client, "verified_fixed", resolved_at=utcnow() - timedelta(days=120))
    summary = _gather_misinformation(client, db, utcnow() - timedelta(days=30))
    assert summary is None


def test_quotes_are_html_escaped(db):
    client = _client(db)
    f = _finding(db, client, "verified_fixed", resolved_at=utcnow())
    f.quote = '<script>alert("x")</script>'
    db.commit()
    summary = _gather_misinformation(client, db, utcnow() - timedelta(days=30))
    html_out = _build_misinformation_html(_data(summary))
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_section_copy_uses_approved_language(db):
    client = _client(db)
    _finding(db, client, "verified_fixed", resolved_at=utcnow())
    summary = _gather_misinformation(client, db, utcnow() - timedelta(days=30))
    html_out = _build_misinformation_html(_data(summary)).lower()
    for banned in ("cited", "citation", "compliance certification", "confidence score"):
        assert banned not in html_out


# --- Weekly digest ----------------------------------------------------------


def test_digest_line_only_for_a_high_finding_confirmed_this_week(db):
    from app.services.digest_service import _protection_line

    client = _client(db)
    assert _protection_line(client, db) is None

    # Confirmed but low severity → no line.
    _finding(db, client, "confirmed", quote="located in Ipoh",
             reviewed_at=utcnow()).severity = "low"
    db.commit()
    assert _protection_line(client, db) is None

    high = _finding(db, client, "confirmed", reviewed_at=utcnow())
    line = _protection_line(client, db)
    assert line is not None and client.name in line

    # Same finding reviewed a month ago → last week's news, no line.
    high.reviewed_at = utcnow() - timedelta(days=30)
    db.commit()
    assert _protection_line(client, db) is None


def test_hallucination_alert_deep_links_to_the_queue(db):
    from app.services.alert_service import _build_hallucination_email

    client = _client(db)
    s = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(s)
    db.commit()
    r = ScanQueryResult(
        scan_id=s.id, platform="chatgpt", category="brand",
        query_text="Is Klinik A any good?", response_text=RESPONSE,
    )
    db.add(r)
    db.commit()

    body = _build_hallucination_email(client, r)
    assert f"/clients/{client.id}/scan" in body


def test_digest_line_never_quotes_the_statement(db):
    from app.services.digest_service import _protection_line

    client = _client(db)
    _finding(db, client, "confirmed", reviewed_at=utcnow())
    line = _protection_line(client, db)
    assert "guarantees full recovery" not in line
