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
