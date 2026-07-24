"""Report v2 sections (spec §4, §7). Each section renders only with data."""
from datetime import date, timedelta
from unittest.mock import patch

# CLAUDE.md §2 left column — never surface these to a client, in any form.
BANNED_TERMS = [
    "cited", "uncited", "mentioned", "citation rate", "ranking position",
    "visibility gap", "confidence score", "char offset", "token count",
    "first mentioned",
]


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _minimal_data(**overrides):
    """A ReportData with only the v1 required fields set."""
    from app.services.report_service import ReportData
    from app.core.time import utcnow
    base = dict(
        period_start=utcnow(), period_end=utcnow(), period_label="July 2026",
        overall_score=70.0, score_band="good", score_color="green",
        ai_citability=70.0, brand_authority=60.0, content_quality=60.0,
        technical_foundations=80.0, structured_data=80.0,
        prev_overall_score=65.0, trend="up", seen_count=7, total_count=10,
        llms_verified=True, schema_verified=True, robots_verified=True,
    )
    base.update(overrides)
    return ReportData(**base)


# 6. A client with nothing new → zero new headers, no error.
def test_no_new_data_renders_no_new_sections():
    from app.services import report_service
    html = report_service._build_report_html(
        type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})(),
        _minimal_data(),
    )
    for header in ("Work Delivered", "Technical Health", "Content Delivered",
                   "Authority Progress", "AI Sources", "Before"):
        assert header not in html


# 5. All sections populated → all six headers present.
def test_all_sections_render_when_populated():
    from app.services import report_service as rs
    data = _minimal_data(
        work_log=[rs.WorkLogLine("Technical", "Verified llms.txt", date(2026, 7, 20))],
        work_log_counts={"technical": 1},
        technical_health=rs.TechnicalHealth(passed=8, warned=1, failed=1,
                                            fixed_checks=["Sitemap reachable"]),
        content_delivered=rs.ContentDelivered(titles=["Dental FAQ pack"],
                                              improvements=["/services: 45 → 78"]),
        authority_progress=rs.AuthorityProgress(newly_live=["LinkedIn"],
                                                newly_verified=["Google Business Profile"],
                                                review_deltas=["Google rating 4.2 → 4.5"]),
        sources_trend=rs.SourcesTrend(share_now=42.0, share_then=31.0,
                                      flips=["cameragear.com"]),
        before_after=[rs.BeforeAfterCard("best dental clinic in KL", "ChatGPT",
                                         "Acme Dental is a leading clinic...")],
    )
    html = rs._build_report_html(
        type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})(),
        data,
    )
    assert "Work Delivered" in html
    assert "Technical Health" in html
    assert "Content Delivered" in html
    assert "Authority Progress" in html
    assert "AI Sources" in html
    assert "Before &amp; After" in html
    # Language rules (CLAUDE.md §2): none of the banned left-column terms
    # may reach a client, in any section.
    html_lower = html.lower()
    for term in BANNED_TERMS:
        assert term not in html_lower, f"banned term {term!r} found in report HTML"


# 7. A gather helper raising → section absent, report still builds, and the
# failure is isolated to ONLY the section that raised.
def test_gather_failure_skips_section_not_report(db):
    """The guard must be reached: give the client a completed scan + score so
    _gather_report_data runs past its early returns and into the v2 gathers."""
    from app.core.time import utcnow
    from app.models.geo_score import GeoScore
    from app.models.scan import Scan
    from app.models.site_audit import SiteAudit
    from app.services import report_service

    client = _make_client(db)
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    db.add(GeoScore(client_id=client.id, scan_id=scan.id, overall_score=70.0,
                    ai_citability=70.0, brand_authority=60.0, content_quality=60.0,
                    technical_foundations=80.0, structured_data=80.0))
    # A recent audit so another v2 section (technical_health) has real data to
    # populate — proving the work_log failure doesn't take other sections down.
    db.add(SiteAudit(client_id=client.id, checks=[], passed=8, warned=1, failed=1,
                     created_at=utcnow()))
    db.commit()

    with patch.object(report_service, "_gather_work_log", side_effect=Exception("boom")):
        data = report_service._gather_report_data(client, db)

    # The failing section is empty, but the report itself still built.
    assert data is not None
    assert data.work_log == []
    assert data.work_log_counts == {}
    # The property under test: skips ONLY its own section — other sections
    # still populate normally.
    assert data.technical_health is not None
    assert data.technical_health.passed == 8


# 8. Period boundary: an entry dated outside the window is excluded.
def test_work_log_gather_respects_period(db):
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    today = utcnow().date()
    inside = work_log_service.suggest(client.id, "technical", "Inside", "r:i", db, entry_date=today)
    work_log_service.update_entry(inside, {"status": "published"}, db)
    outside = work_log_service.suggest(
        client.id, "technical", "Outside", "r:o", db, entry_date=today - timedelta(days=60))
    work_log_service.update_entry(outside, {"status": "published"}, db)

    lines, counts = report_service._gather_work_log(client, db, today - timedelta(days=30))
    descriptions = [line.description for line in lines]
    assert "Inside" in descriptions
    assert "Outside" not in descriptions
    assert counts.get("technical") == 1


# 9. Technical health must be period-scoped: a SiteAudit from before the period
# is excluded even if it's the latest audit.
def test_technical_health_excludes_audits_before_period(db):
    """Regression test for: _gather_technical_health returns None when latest
    SiteAudit.created_at < since, preventing stale audits from appearing as
    "Fixed this period:" improvements."""
    from app.core.time import utcnow
    from app.models.site_audit import SiteAudit
    from app.services import report_service

    client = _make_client(db)
    now = utcnow()
    period_start = now - timedelta(days=30)

    # Create a SiteAudit from 90 days ago (clearly before the 30-day period).
    old_audit = SiteAudit(
        client_id=client.id,
        checks=[],
        passed=8, warned=1, failed=1,
        created_at=now - timedelta(days=90)
    )
    db.add(old_audit)
    db.commit()

    # Query with a period_start of 30 days ago: the old audit should be excluded.
    result = report_service._gather_technical_health(client, db, period_start)
    assert result is None, "SiteAudit from 90 days ago should be excluded from a 30-day period"

    # Now add a recent audit (within the period) and verify it returns non-None.
    recent_audit = SiteAudit(
        client_id=client.id,
        checks=[],
        passed=8, warned=1, failed=1,
        created_at=period_start + timedelta(days=15)  # 15 days into the period
    )
    db.add(recent_audit)
    db.commit()

    result = report_service._gather_technical_health(client, db, period_start)
    assert result is not None, "SiteAudit within the period should be included"
    assert result.passed == 8


# 10. Content delivered improvements must deduplicate per URL (newest vs
# second-newest only), even with 3+ audits.
def test_content_delivered_deduplicates_multi_audit_urls(db):
    """Regression test for: _gather_content_delivered compares newest vs
    second-newest only, ensuring a URL audited 3+ times contributes at most
    one improvement line instead of one per older row."""
    from app.core.time import utcnow
    from app.models.page_audit import PageAudit
    from app.services import report_service

    client = _make_client(db)
    now = utcnow()
    period_start = now - timedelta(days=30)

    # Create three audits for the same URL with increasing scores and times.
    url = "https://acme.com/services"
    base_time = period_start + timedelta(days=5)

    audit1 = PageAudit(
        client_id=client.id,
        url=url,
        score=30,
        checks=[],
        suggestions=[],
        created_at=base_time
    )
    db.add(audit1)
    db.commit()

    audit2 = PageAudit(
        client_id=client.id,
        url=url,
        score=45,
        checks=[],
        suggestions=[],
        created_at=base_time + timedelta(days=10)
    )
    db.add(audit2)
    db.commit()

    audit3 = PageAudit(
        client_id=client.id,
        url=url,
        score=78,
        checks=[],
        suggestions=[],
        created_at=base_time + timedelta(days=20)
    )
    db.add(audit3)
    db.commit()

    # Call _gather_content_delivered with the period_start.
    result = report_service._gather_content_delivered(client, db, period_start)

    # Should have exactly ONE improvement line for this URL (newest vs second-newest).
    assert result is not None
    improvements_for_url = [i for i in result.improvements if "/services" in i]
    assert len(improvements_for_url) == 1, \
        f"Expected 1 improvement line for /services, got {len(improvements_for_url)}: {improvements_for_url}"

    # The improvement should compare 45 → 78 (second-newest vs newest),
    # not 30 → 78 or 30 → 45.
    line = improvements_for_url[0]
    assert "45 → 78" in line, \
        f"Expected improvement to show '45 → 78', got: {line}"
