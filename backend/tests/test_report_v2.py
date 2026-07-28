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


def _publish_on(db, entry, published_on):
    """Publish, then backdate published_at — update_entry always stamps now."""
    from datetime import datetime
    from app.services import work_log_service
    work_log_service.update_entry(entry, {"status": "published"}, db)
    entry.published_at = datetime(published_on.year, published_on.month, published_on.day, 12, 0)
    db.commit()
    db.refresh(entry)
    return entry


# 8. Period boundary: an entry already reported in an earlier period is excluded.
def test_work_log_gather_respects_period(db):
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    today = utcnow().date()
    inside = work_log_service.suggest(client.id, "technical", "Inside", "r:i", db, entry_date=today)
    _publish_on(db, inside, today)
    outside = work_log_service.suggest(
        client.id, "technical", "Outside", "r:o", db, entry_date=today - timedelta(days=60))
    _publish_on(db, outside, today - timedelta(days=60))

    lines, counts = report_service._gather_work_log(client, db, today - timedelta(days=30))
    descriptions = [line.description for line in lines]
    assert "Inside" in descriptions
    assert "Outside" not in descriptions
    assert counts.get("technical") == 1


# 8b. The Review Queue case: work whose hook fired before the window but that
# was published inside it belongs in THIS report — its own period's report has
# already shipped, so entry_date scoping meant it reached no PDF at all.
def test_work_log_gather_includes_late_published_old_work(db):
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    today = utcnow().date()
    late = work_log_service.suggest(
        client.id, "authority", "Listed you in three directories",
        "r:late", db, entry_date=today - timedelta(days=75))
    _publish_on(db, late, today)

    lines, counts = report_service._gather_work_log(
        client, db, today - timedelta(days=30), today)
    assert [line.description for line in lines] == ["Listed you in three directories"]
    # Displayed date is when the work happened, not when it was approved.
    assert lines[0].entry_date == today - timedelta(days=75)
    assert counts.get("authority") == 1


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


# 11. A hallucination-flagged result must never be quoted as a Before & After
# win, even if the diff reports its query as newly seen (regression: the same
# report can't flag an answer as false AND quote it as a proof of a win).
def test_before_after_excludes_hallucination_flagged_results(db):
    from unittest.mock import patch as mock_patch
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.schemas.scan import ScanDiffQuery, ScanDiffResponse
    from app.services import report_service

    client = _make_client(db)
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()

    flagged = ScanQueryResult(
        scan_id=scan.id, platform="chatgpt", category="brand",
        query_text="best dental clinic in KL",
        response_text="Acme Dental is a leading clinic known for excellent patient care.",
        brand_detected=True, hallucination_flagged=True,
    )
    clean = ScanQueryResult(
        scan_id=scan.id, platform="chatgpt", category="brand",
        query_text="best dentist near me",
        response_text="Acme Dental is a trusted dentist offering modern, friendly care.",
        brand_detected=True, hallucination_flagged=False,
    )
    db.add_all([flagged, clean])
    db.commit()

    fake_diff = ScanDiffResponse(
        latest_scan_id=scan.id,
        newly_seen=[
            ScanDiffQuery(platform="chatgpt", category="brand", query_text="best dental clinic in KL"),
            ScanDiffQuery(platform="chatgpt", category="brand", query_text="best dentist near me"),
        ],
        has_comparison=True,
    )
    with mock_patch(
        "app.services.scan_diff_service.compute_scan_diff", return_value=fake_diff
    ):
        cards = report_service._gather_before_after(client, db, utcnow())

    query_texts = [c.query_text for c in cards]
    assert "best dentist near me" in query_texts
    assert "best dental clinic in KL" not in query_texts


def _make_asset(db, client, **overrides):
    from app.models.authority_asset import AuthorityAsset
    kwargs = dict(client_id=client.id, asset_key="gbp", name="Google Business Profile",
                  asset_type="review_platform", status="verified")
    kwargs.update(overrides)
    a = AuthorityAsset(**kwargs)
    db.add(a)
    db.commit()
    return a


# 12. Authority progress must not re-report old wins. AuthorityAsset.updated_at
# is re-dated by every verify_asset run (it always assigns last_checked_at and
# found_nap), so a routine re-verification of a months-old asset would otherwise
# print it as "verified this period" in every subsequent report.
def test_authority_progress_ignores_stale_updated_at(db):
    from app.core.time import utcnow
    from app.services import report_service
    client = _make_client(db)
    # Freshly-dated row (as a re-verification leaves it) but no work-log entry
    # in the period — nothing actually happened this month.
    _make_asset(db, client, status="verified")

    assert report_service._gather_authority_progress(client, db, utcnow() - timedelta(days=30)) is None


def test_authority_progress_reads_published_work_log(db):
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    asset = _make_asset(db, client, status="verified", name="LinkedIn Company Page")
    entry = work_log_service.suggest(
        client.id, "authority", f"{asset.name} — now verified",
        f"authority_verified:{asset.id}", db, entry_date=utcnow().date())
    work_log_service.update_entry(entry, {"status": "published"}, db)

    got = report_service._gather_authority_progress(client, db, utcnow() - timedelta(days=30))
    assert got is not None
    assert got.newly_verified == ["LinkedIn Company Page"]


def test_authority_progress_ignores_unpublished_work_log(db):
    """A suggestion Faris never published must not reach the client's report."""
    from app.core.time import utcnow
    from app.services import report_service, work_log_service
    client = _make_client(db)
    asset = _make_asset(db, client, status="live")
    work_log_service.suggest(client.id, "authority", f"{asset.name} — now live",
                             f"authority_live:{asset.id}", db, entry_date=utcnow().date())

    assert report_service._gather_authority_progress(client, db, utcnow() - timedelta(days=30)) is None


# 13. Review-snapshot deltas must be period-scoped too, or a February snapshot
# pair reprints identically in every report from March onward.
def test_authority_review_deltas_respect_period(db):
    from app.core.time import utcnow
    from app.services import report_service
    client = _make_client(db)
    old = (utcnow().date() - timedelta(days=60)).isoformat()
    _make_asset(db, client, review_snapshots=[
        {"date": (utcnow().date() - timedelta(days=90)).isoformat(), "rating": 4.2, "count": 88},
        {"date": old, "rating": 4.5, "count": 94},
    ])

    assert report_service._gather_authority_progress(client, db, utcnow() - timedelta(days=30)) is None


def test_authority_review_deltas_included_when_recent(db):
    from app.core.time import utcnow
    from app.services import report_service
    client = _make_client(db)
    _make_asset(db, client, review_snapshots=[
        {"date": (utcnow().date() - timedelta(days=40)).isoformat(), "rating": 4.2, "count": 88},
        {"date": utcnow().date().isoformat(), "rating": 4.5, "count": 94},
    ])

    got = report_service._gather_authority_progress(client, db, utcnow() - timedelta(days=30))
    assert got is not None
    assert len(got.review_deltas) == 1
    assert "4.2" in got.review_deltas[0] and "4.5" in got.review_deltas[0]


# 14. The header counts every published entry but the table is capped at
# _MAX_WORK_LOG_LINES — a client reading "Technical: 12" above 10 rows would
# reasonably conclude the report is wrong. Disclose the remainder.
def test_work_log_html_discloses_truncated_rows():
    from app.services import report_service as rs
    lines = [rs.WorkLogLine("Technical", f"Did thing {i}", date(2026, 7, 20))
             for i in range(rs._MAX_WORK_LOG_LINES)]
    html_out = rs._build_work_log_html(
        _minimal_data(work_log=lines, work_log_counts={"technical": 12}))

    assert "2 more" in html_out
    for term in BANNED_TERMS:
        assert term not in html_out.lower()


def test_work_log_html_no_overflow_note_when_complete():
    from app.services import report_service as rs
    lines = [rs.WorkLogLine("Technical", f"Did thing {i}", date(2026, 7, 20)) for i in range(3)]
    html_out = rs._build_work_log_html(
        _minimal_data(work_log=lines, work_log_counts={"technical": 3}))

    assert "more" not in html_out.lower()
