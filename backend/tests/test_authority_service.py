"""authority_service — catalog, CRUD (spec §4, §10). Real db fixture."""


def _make_client(db, industry="Dental clinic"):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry=industry, contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_catalog_lists_all_items_unadded_for_new_client(db):
    from app.services import authority_service
    client = _make_client(db)
    catalog = authority_service.get_catalog(client, db)
    from app.core.constants import AUTHORITY_ASSET_CATALOG
    assert len(catalog) == len(AUTHORITY_ASSET_CATALOG)
    assert all(item["added"] is False for item in catalog)


def test_catalog_sorts_industry_matches_first(db):
    from app.services import authority_service
    client = _make_client(db, industry="Healthcare / dental clinic")
    catalog = authority_service.get_catalog(client, db)
    # myhealth_clinic (suggested_industries includes "dental"/"clinic") sorts
    # ahead of an item with no industry hint.
    keys = [i["key"] for i in catalog]
    assert keys.index("myhealth_clinic") < keys.index("linkedin")


def test_add_selected_catalog_keys_creates_exactly_those(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}, {"asset_key": "linkedin"}], db)
    rows = db.query(AuthorityAsset).filter(AuthorityAsset.client_id == client.id).all()
    assert {r.asset_key for r in rows} == {"gbp", "linkedin"}
    gbp = next(r for r in rows if r.asset_key == "gbp")
    assert gbp.name == "Google Business Profile"
    assert gbp.asset_type == "review_platform"
    assert gbp.provenance_domain == "google.com"
    assert gbp.status == "missing"


def test_add_is_idempotent_on_catalog_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    assert db.query(AuthorityAsset).filter(
        AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key == "gbp"
    ).count() == 1


def test_add_custom_asset_has_null_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    rows = authority_service.add_assets(
        client,
        [{"name": "Klinik directory XYZ", "asset_type": "directory",
          "url": "https://xyz.example/acme", "provenance_domain": "xyz.example"}],
        db,
    )
    assert len(rows) == 1
    row = db.query(AuthorityAsset).one()
    assert row.asset_key is None
    assert row.name == "Klinik directory XYZ"
    assert row.provenance_domain == "xyz.example"


def test_update_status_writes_activity_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "in_progress"}, db)
    log = db.query(ActivityLog).filter(
        ActivityLog.client_id == client.id,
        ActivityLog.event_type == "authority_status_changed",
    ).one()
    assert "in progress" in log.note.lower()
    assert asset.status == "in_progress"


def test_update_same_status_writes_no_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"url": "https://g.co/acme"}, db)  # no status change
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed"
    ).count() == 0
    assert asset.url == "https://g.co/acme"


def test_hidden_assets_excluded_by_default(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"hidden": True}, db)
    assert authority_service.list_assets(client.id, db) == []
    assert len(authority_service.list_assets(client.id, db, include_hidden=True)) == 1


def test_update_ignores_invalid_status(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "bogus"}, db)
    assert asset.status == "missing"  # unchanged — invalid status ignored
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed"
    ).count() == 0


from unittest.mock import patch

from app.services.url_safety import SafeResponse

_PAGE_WITH_NAME = (
    "<html><body><h1>Acme Dental Clinic</h1>"
    "<p>Call us at +60 3-1234 5678. 12 Jalan Ampang, Kuala Lumpur.</p>"
    "</body></html>"
)
_PAGE_WITHOUT_NAME = "<html><body><p>Some unrelated directory listing.</p></body></html>"
_PAGE_WRONG_PHONE = (
    "<html><body><h1>Acme Dental Clinic</h1>"
    "<p>Phone: 03-9999 0000</p></body></html>"
)


def _ok(html):
    return SafeResponse(200, html, {"content-type": "text/html"})


def test_verify_marks_verified_when_name_present(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITH_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "verified"
    assert asset.last_checked_at is not None
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed",
        ActivityLog.note.like("%verified%"),
    ).count() == 1


def test_verify_name_absent_keeps_status_and_notes(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITHOUT_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "live"  # never auto-upgraded, never downgraded
    assert "couldn't" in note.lower() or "could not" in note.lower()


def test_verify_without_url_returns_note(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    asset, note = authority_service.verify_asset(asset, client, db)
    assert "url" in note.lower()
    assert asset.status == "missing"


def test_verify_fetch_failure_only_sets_last_checked(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", side_effect=Exception("timeout")):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.status == "live"
    assert asset.last_checked_at is not None
    assert "reach" in note.lower() or "load" in note.lower()


def test_nap_mismatch_flagged_on_different_phone(db):
    from app.services import authority_service
    client = _make_client(db)
    client.phone = "+60 3-1234 5678"
    db.commit()
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WRONG_PHONE)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.nap_mismatch is True


def test_nap_match_when_same_digits_formatted_differently(db):
    from app.services import authority_service
    client = _make_client(db)
    client.phone = "03-1234 5678"  # same 9 significant digits as +60 3-1234 5678
    db.commit()
    (asset,) = authority_service.add_assets(
        client, [{"asset_key": "gbp", "url": "https://g.co/acme"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    with patch.object(authority_service, "is_safe_crawl_url", return_value=True), \
         patch.object(authority_service, "safe_get", return_value=_ok(_PAGE_WITH_NAME)):
        asset, note = authority_service.verify_asset(asset, client, db)
    assert asset.nap_mismatch is False


def test_review_snapshot_appends_in_order(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.add_review_snapshot(asset, 4.2, 31, db)
    authority_service.add_review_snapshot(asset, 4.5, 58, db)
    assert [s["count"] for s in asset.review_snapshots] == [31, 58]
    assert asset.review_snapshots[0]["rating"] == 4.2
    assert "date" in asset.review_snapshots[0]


def _seed_sources(db, client, domain_counts: dict[str, int]):
    """Create one completed scan whose client-owned queries cite the given
    domains the given number of times."""
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.scan_query_source import ScanQuerySource
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    result = ScanQueryResult(
        scan_id=scan.id, platform="perplexity", category="recommendation",
        query_text="best dental clinic KL", response_text="...", brand_detected=False,
    )
    db.add(result)
    db.commit()
    rank = 1
    for domain, n in domain_counts.items():
        for _ in range(n):
            db.add(ScanQuerySource(
                scan_query_result_id=result.id, url=f"https://{domain}/x{rank}",
                domain=domain, rank=rank, source_type="third_party", fetch_status="ok",
            ))
            rank += 1
    db.commit()
    return scan


def test_provenance_counts_roll_up_per_domain(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"cameragear.com": 3, "reddit.com": 2})
    counts = authority_service.compute_provenance_counts(client.id, db)
    assert counts == {"cameragear.com": 3, "reddit.com": 2}


def test_asset_seen_count_uses_suffix_match(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"maps.google.com": 4})
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)  # google.com
    view = authority_service.build_authority_view(client, db)
    gbp = next(a for a in view["assets"] if a["asset_key"] == "gbp")
    assert gbp["seen_in_ai_sources"] == 4


def test_suggested_next_excludes_covered_and_needs_an_asset(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"reddit.com": 5, "linkedin.com": 3})
    # No assets yet → no suggestions at all (spec §5).
    assert authority_service.build_authority_view(client, db)["suggested_next"] == []
    # Add + mark LinkedIn live → linkedin.com is covered, reddit.com surfaces.
    (li,) = authority_service.add_assets(client, [{"asset_key": "linkedin"}], db)
    authority_service.update_asset(li, {"status": "live"}, db)
    view = authority_service.build_authority_view(client, db)
    domains = [s["domain"] for s in view["suggested_next"]]
    assert "reddit.com" in domains
    assert "linkedin.com" not in domains
    reddit = next(s for s in view["suggested_next"] if s["domain"] == "reddit.com")
    assert reddit["count"] == 5
    assert reddit["catalog_key"] is None  # reddit isn't in the catalog


def test_suggested_next_maps_catalog_key_when_domain_known(db):
    from app.services import authority_service
    client = _make_client(db)
    _seed_sources(db, client, {"crunchbase.com": 6})
    (li,) = authority_service.add_assets(client, [{"asset_key": "linkedin"}], db)
    authority_service.update_asset(li, {"status": "live"}, db)
    view = authority_service.build_authority_view(client, db)
    cb = next(s for s in view["suggested_next"] if s["domain"] == "crunchbase.com")
    assert cb["catalog_key"] == "crunchbase"


def test_summary_counts_live_and_verified(db):
    from app.services import authority_service
    client = _make_client(db)
    a1, a2 = authority_service.add_assets(
        client, [{"asset_key": "gbp"}, {"asset_key": "linkedin"}], db)
    authority_service.update_asset(a1, {"status": "verified"}, db)
    authority_service.update_asset(a2, {"status": "live"}, db)
    summary = authority_service.build_authority_view(client, db)["summary"]
    assert summary["live"] == 1
    assert summary["verified"] == 1
    assert summary["total"] == 2


def test_summarize_for_assessment_none_when_empty(db):
    from app.services import authority_service
    client = _make_client(db)
    assert authority_service.summarize_for_assessment(client.id, db) is None


def test_summarize_for_assessment_reports_verified_names(db):
    from app.services import authority_service
    client = _make_client(db)
    (gbp,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(gbp, {"status": "verified"}, db)
    summary = authority_service.summarize_for_assessment(client.id, db)
    assert summary["verified"] == 1
    assert "Google Business Profile" in summary["verified_names"]
