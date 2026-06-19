import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


# ── _compute_trend ─────────────────────────────────────────────────────────────

def test_trend_up_when_overall_increases_more_than_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(72.0, 60.0) == "up"


def test_trend_down_when_overall_decreases_more_than_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(55.0, 70.0) == "down"


def test_trend_flat_within_half_point():
    from app.services.report_service import _compute_trend
    assert _compute_trend(60.3, 60.0) == "flat"


def test_trend_first_when_no_previous():
    from app.services.report_service import _compute_trend
    assert _compute_trend(50.0, None) == "first"


# ── _gather_report_data ────────────────────────────────────────────────────────

def test_gather_report_data_returns_none_when_no_recent_scan():
    from app.services.report_service import _gather_report_data
    client = MagicMock()
    client.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    assert _gather_report_data(client, db) is None


def test_gather_report_data_returns_none_when_no_geo_score():
    from app.services.report_service import _gather_report_data
    client = MagicMock()
    client.id = uuid.uuid4()
    db = MagicMock()
    mock_scan = MagicMock()
    mock_scan.id = uuid.uuid4()

    # Scan query uses .filter().order_by().first() — returns mock_scan
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_scan
    # GeoScore query uses .filter().first() (no order_by) — return None
    db.query.return_value.filter.return_value.first.return_value = None

    assert _gather_report_data(client, db) is None


# ── _build_report_html ────────────────────────────────────────────────────────

def _make_report_data():
    from app.services.report_service import ReportData, CompetitorSummary
    return ReportData(
        period_start=datetime(2026, 5, 1),
        period_end=datetime(2026, 5, 31),
        period_label="May 2026",
        overall_score=72.5,
        score_band="good",
        score_color="green",
        ai_citability=75.0,
        brand_authority=60.0,
        content_quality=70.0,
        technical_foundations=100.0,
        structured_data=0.0,
        prev_overall_score=65.0,
        trend="up",
        seen_count=6,
        total_count=8,
        llms_verified=True,
        schema_verified=False,
        robots_verified=True,
        competitors=[CompetitorSummary(name="Rival Co", ai_citability=80.0, is_winning=True)],
        recommendation="Publish a blog post.",
    )


def test_build_report_html_contains_client_name():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Acme Corp" in html


def test_build_report_html_contains_period_label():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "May 2026" in html


def test_build_report_html_contains_overall_score():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "72" in html


def test_build_report_html_contains_all_required_sections():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "AI Visibility Score" in html
    assert "Score Breakdown" in html
    assert "AI Visibility Frequency" in html
    assert "Competitor Comparison" in html
    assert "AI Readiness Toolkit" in html
    assert "Recommended Action" in html


def test_build_report_html_shows_seen_count():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "6/8" in html


def test_build_report_html_shows_competitor():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Rival Co" in html


def test_build_report_html_shows_recommendation():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Publish a blog post." in html


def test_build_report_html_shows_toolkit_verified_status():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    # llms_verified=True, schema_verified=False
    assert html.count("Verified") >= 1
    assert "Not Verified" in html


def test_build_report_html_contains_manual_assessment_label():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    html = _build_report_html(client, _make_report_data())
    assert "Assessed by SeenBy team" in html


# ── generate_report_pdf ───────────────────────────────────────────────────────

def test_generate_report_pdf_returns_none_for_archived_client():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.archived_at = datetime.utcnow()
    db.get.return_value = client
    assert generate_report_pdf(uuid.uuid4(), db) is None


def test_generate_report_pdf_returns_none_when_no_scan_data():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.archived_at = None
    db.get.return_value = client
    with patch("app.services.report_service._gather_report_data", return_value=None):
        assert generate_report_pdf(uuid.uuid4(), db) is None


def test_generate_report_pdf_uploads_to_r2_and_returns_report():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = "Acme Corp"
    client.archived_at = None
    client.is_prospect = False
    db.get.return_value = client

    with patch("app.services.report_service._gather_report_data", return_value=_make_report_data()), \
         patch("app.services.report_service.weasyprint") as mock_wp, \
         patch("app.services.report_service.upload_pdf", return_value="https://pub.seenby.my/reports/test.pdf") as mock_upload:
        mock_wp.HTML.return_value.write_pdf.return_value = b"fake-pdf-bytes"
        result = generate_report_pdf(client.id, db)

    mock_upload.assert_called_once()
    assert mock_upload.call_args[0][1] == b"fake-pdf-bytes"
    db.add.assert_called()
    db.commit.assert_called()


def test_generate_report_pdf_logs_report_generated_activity():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.id = uuid.uuid4()
    client.archived_at = None
    client.is_prospect = False
    db.get.return_value = client

    added_objects = []
    db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.report_service._gather_report_data", return_value=_make_report_data()), \
         patch("app.services.report_service.weasyprint") as mock_wp, \
         patch("app.services.report_service.upload_pdf", return_value="https://pub.seenby.my/r.pdf"):
        mock_wp.HTML.return_value.write_pdf.return_value = b"pdf"
        generate_report_pdf(client.id, db)

    event_types = [o.event_type for o in added_objects if hasattr(o, "event_type")]
    assert "report_generated" in event_types


# ── change narrative ──────────────────────────────────────────────────────────

def test_fallback_narrative_first_report():
    from app.services.report_service import _fallback_narrative, ReportData
    data = _make_report_data()
    data.trend = "first"
    data.prev_overall_score = None
    text = _fallback_narrative(data)
    assert "first" in text.lower()
    assert "6 of 8" in text


def test_fallback_narrative_uses_seen_by_ai_language():
    from app.services.report_service import _fallback_narrative
    data = _make_report_data()
    text = _fallback_narrative(data)
    assert "seen by AI" in text
    # terminology guard — never leak forbidden terms
    assert "cited" not in text.lower()
    assert "ranking" not in text.lower()


def test_generate_change_narrative_first_report_skips_claude():
    from app.services.report_service import _generate_change_narrative
    data = _make_report_data()
    data.trend = "first"
    data.prev_overall_score = None
    with patch("app.services.report_service.anthropic_client") as mock_client:
        text = _generate_change_narrative(data)
    mock_client.assert_not_called()
    assert "first" in text.lower()


def test_generate_change_narrative_falls_back_on_api_error():
    from app.services.report_service import _generate_change_narrative
    data = _make_report_data()  # trend="up", prev=65.0 → would call Claude
    with patch("app.services.report_service.anthropic_client", side_effect=RuntimeError("api down")):
        text = _generate_change_narrative(data)
    # deterministic fallback, not an exception
    assert "72" in text and "65" in text


def test_generate_change_narrative_returns_claude_text():
    from app.services.report_service import _generate_change_narrative
    data = _make_report_data()
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="Your visibility improved this month, seen by AI in more queries.")]
    with patch("app.services.report_service.anthropic_client") as mock_client:
        mock_client.return_value.messages.create.return_value = fake_msg
        text = _generate_change_narrative(data)
    assert text == "Your visibility improved this month, seen by AI in more queries."


def test_build_report_html_renders_narrative_when_present():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.change_narrative = "Your score rose because more platforms saw your brand."
    html = _build_report_html(client, data)
    assert "What Changed This Month" in html
    assert "Your score rose because more platforms saw your brand." in html


def test_build_report_html_omits_narrative_section_when_empty():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.change_narrative = ""
    html = _build_report_html(client, data)
    assert "What Changed This Month" not in html


def test_generate_report_pdf_persists_narrative_on_report():
    from app.services.report_service import generate_report_pdf
    db = MagicMock()
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = "Acme Corp"
    client.archived_at = None
    client.is_prospect = False
    db.get.return_value = client

    data = _make_report_data()
    data.change_narrative = "Narrative for the month."
    added = []
    db.add.side_effect = lambda obj: added.append(obj)

    with patch("app.services.report_service._gather_report_data", return_value=data), \
         patch("app.services.report_service.weasyprint") as mock_wp, \
         patch("app.services.report_service.upload_pdf", return_value="https://pub.seenby.my/r.pdf"):
        mock_wp.HTML.return_value.write_pdf.return_value = b"pdf"
        generate_report_pdf(client.id, db)

    reports = [o for o in added if hasattr(o, "change_narrative")]
    assert reports and reports[0].change_narrative == "Narrative for the month."


# ── Score Trend chart ─────────────────────────────────────────────────────────

def test_build_report_html_renders_trend_chart_with_history():
    from app.services.report_service import _build_report_html, TrendPoint
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.score_history = [
        TrendPoint(label="1 Apr", score=42.0, color="yellow"),
        TrendPoint(label="1 May", score=58.0, color="yellow"),
    ]
    html = _build_report_html(client, data)
    assert "Score Trend" in html
    assert "<svg" in html
    assert "1 Apr" in html and "1 May" in html


def test_build_report_html_omits_trend_chart_with_single_point():
    from app.services.report_service import _build_report_html, TrendPoint
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.score_history = [TrendPoint(label="1 May", score=58.0, color="yellow")]
    html = _build_report_html(client, data)
    assert "Score Trend" not in html


# ── Content Gaps ──────────────────────────────────────────────────────────────

def test_build_report_html_renders_content_gaps():
    from app.services.report_service import _build_report_html, ContentGap
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.content_gaps = [
        ContentGap(query_text="Best dentist in KL", platform="ChatGPT", competitors_seen=["Rival Co"]),
    ]
    html = _build_report_html(client, data)
    assert "Your Competitors Are Winning Here" in html
    assert "Best dentist in KL" in html
    assert "Rival Co" in html


def test_build_report_html_omits_content_gaps_when_empty():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.content_gaps = []
    html = _build_report_html(client, data)
    assert "Your Competitors Are Winning Here" not in html


# ── Hallucinations ────────────────────────────────────────────────────────────

def test_build_report_html_renders_hallucinations_query_only():
    from app.services.report_service import _build_report_html, HallucinationLine
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.hallucinations = [
        HallucinationLine(
            platform="Perplexity",
            query_text="Does Acme Corp offer 24/7 support?",
            status="in_progress",
            status_label="In progress",
        )
    ]
    html = _build_report_html(client, data)
    assert "Inaccurate AI Answers Flagged" in html
    assert "Does Acme Corp offer 24/7 support?" in html
    assert "Perplexity" in html
    # remediation status is surfaced
    assert "In progress" in html


def test_build_report_html_omits_hallucinations_when_none():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.hallucinations = []
    html = _build_report_html(client, data)
    assert "Inaccurate AI Answers Flagged" not in html


# ── AI Referral pipeline (revenue) ─────────────────────────────────────────────

def test_build_report_html_renders_pipeline_rm_when_configured():
    from app.services.report_service import _build_report_html
    from app.services.revenue_service import PipelineEstimate
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.ai_visitors_current = 1000
    data.pipeline = PipelineEstimate(
        ai_visitors=1000, est_leads=20, est_pipeline_rm=100_000, est_won_rm=20_000,
        avg_deal_value_rm=5000, visitor_to_lead_pct=2, lead_to_customer_pct=20,
    )
    html = _build_report_html(client, data)
    assert "Estimated Pipeline From AI This Month" in html
    assert "RM 100,000" in html
    assert "RM 20,000" in html


def test_build_report_html_traffic_section_always_present():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()  # ai_visitors_current=None, pipeline=None
    html = _build_report_html(client, data)
    # Section is shown even with no data (degrades to a tracking-begins state).
    assert "AI Referral Traffic" in html
    assert "Tracking begins soon" in html


# ── Content gaps: status + won-back proof ──────────────────────────────────────

def test_build_report_html_content_gap_shows_status_and_won_back():
    from app.services.report_service import _build_report_html, ContentGap
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()
    data.content_gaps = [
        ContentGap(query_text="Best dentist in KL", platform="ChatGPT",
                   competitors_seen=["Rival Co"], status="in_progress", status_label="In progress"),
    ]
    data.gaps_won_back = 2
    html = _build_report_html(client, data)
    assert "Your Competitors Are Winning Here" in html
    assert "In progress" in html
    assert "won back this period" in html
    assert "2 previously-lost questions won back" in html


# ── Manual-dimension evidence fallback ─────────────────────────────────────────

def test_build_report_html_manual_evidence_never_naked():
    from app.services.report_service import _build_report_html
    client = MagicMock()
    client.name = "Acme Corp"
    data = _make_report_data()  # no evidence text set
    html = _build_report_html(client, data)
    # Label present, and a substantive methodology line backs it (not bare).
    assert "Assessed by SeenBy team" in html
    assert "Based on brand presence" in html
    assert "Based on content depth" in html


# ── send_report_email ─────────────────────────────────────────────────────────

def _make_mock_report(sent_at=None):
    r = MagicMock()
    r.id = uuid.uuid4()
    r.client_id = uuid.uuid4()
    r.r2_key = "reports/client/20260601.pdf"
    r.r2_url = "https://pub.seenby.my/reports/client/20260601.pdf"
    r.period_start = datetime(2026, 5, 1)
    r.overall_score = 72.0
    r.sent_at = sent_at
    return r


def test_send_report_email_returns_false_when_already_sent():
    from app.services.report_service import send_report_email
    db = MagicMock()
    db.get.return_value = _make_mock_report(sent_at=datetime.utcnow())
    assert send_report_email(uuid.uuid4(), db) is False


def test_send_report_email_returns_false_when_no_contact_email():
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.contact_email = None
    db.get.side_effect = [report, client]
    assert send_report_email(uuid.uuid4(), db) is False


def test_send_report_email_sends_email_with_pdf_attachment():
    import resend as resend_module
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.name = "Acme Corp"
    client.contact_email = "client@acme.com"
    db.get.side_effect = [report, client]

    with patch("app.services.report_service.download_pdf", return_value=b"pdf-bytes"), \
         patch.object(resend_module.Emails, "send") as mock_send:
        result = send_report_email(uuid.uuid4(), db)

    assert result is True
    call_kwargs = mock_send.call_args[0][0]
    assert call_kwargs["to"] == ["client@acme.com"]
    assert "May 2026" in call_kwargs["subject"]
    assert len(call_kwargs["attachments"]) == 1
    assert call_kwargs["attachments"][0]["filename"].endswith(".pdf")


def test_send_report_email_marks_report_sent_and_logs_activity():
    import resend as resend_module
    from app.services.report_service import send_report_email
    db = MagicMock()
    report = _make_mock_report()
    client = MagicMock()
    client.name = "Acme Corp"
    client.contact_email = "client@acme.com"
    db.get.side_effect = [report, client]

    added_objects = []
    db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.report_service.download_pdf", return_value=b"pdf-bytes"), \
         patch.object(resend_module.Emails, "send"):
        send_report_email(uuid.uuid4(), db)

    assert report.sent_at is not None
    event_types = [o.event_type for o in added_objects if hasattr(o, "event_type")]
    assert "report_sent" in event_types
    db.commit.assert_called()
