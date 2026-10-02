"""Placement engine: discovery (Task 2), scoring (Task 3) and lifecycle."""
import uuid
from datetime import datetime, timedelta

from app.models.authority_asset import AuthorityAsset
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.placement_target import PlacementTarget
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services import placement_service as ps

_BASE = datetime(2026, 9, 1)


def _client(db):
    client = Client(id=uuid.uuid4(), name="Acme Dental", website="https://acme.com", industry="dentist")
    rival = Competitor(id=uuid.uuid4(), client_id=client.id, name="Rival Dental", website="https://rival.com")
    db.add_all([client, rival])
    db.commit()
    return client, rival


def _scan(db, client, day=0):
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed",
                completed_at=_BASE + timedelta(days=day))
    db.add(scan)
    db.commit()
    return scan


def _answer(db, scan, *, platform="chatgpt", category="recommendation", seen=False,
            sources=(), query="best dentist in KL"):
    """sources: (url, domain, title, client_on_page, [competitor ids])"""
    sqr = ScanQueryResult(scan_id=scan.id, platform=platform, category=category,
                          query_text=query, response_text="…", brand_detected=seen,
                          sources_captured=True)
    for rank, (url, domain, title, client_on, comps) in enumerate(sources, start=1):
        sqr.sources.append(ScanQuerySource(
            url=url, domain=domain, title=title, rank=rank, source_type="third_party",
            fetch_status="ok", present_brands={"client": client_on, "competitors": comps}))
    db.add(sqr)
    db.commit()
    return sqr


_LIST = ("https://kl-guide.example/best-dentists", "kl-guide.example",
         "10 Best Dentists in KL (2026)")


# ── Task 2: discovery ────────────────────────────────────────────────────────

def test_page_without_the_client_becomes_a_target(db):
    client, rival = _client(db)
    scan = _scan(db, client)
    sqr = _answer(db, scan, sources=[(*_LIST, False, [str(rival.id)])])

    ps.refresh_targets(scan.id, client.id, db)

    t = db.query(PlacementTarget).one()
    assert (t.url, t.domain, t.title) == _LIST
    assert t.category == "listicle"
    assert t.status == "open"
    assert t.answers_count == 1
    assert t.platforms == ["chatgpt"]
    assert t.query_categories == ["recommendation"]
    assert t.competitors_present == [str(rival.id)]
    assert t.representative_result_id == sqr.id
    assert t.first_seen_scan_id == scan.id and t.last_seen_scan_id == scan.id


def test_page_listing_only_untracked_businesses_is_still_a_target(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    _answer(db, scan, sources=[(*_LIST, False, [])])

    ps.refresh_targets(scan.id, client.id, db)

    assert db.query(PlacementTarget).one().competitors_present == []


def test_page_that_already_names_the_client_is_not_a_target(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    _answer(db, scan, sources=[(*_LIST, True, [])])

    ps.refresh_targets(scan.id, client.id, db)

    assert db.query(PlacementTarget).count() == 0


def test_owned_and_unchecked_sources_are_ignored(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    sqr = _answer(db, scan)
    sqr.sources.append(ScanQuerySource(url="https://acme.com/a", domain="acme.com", rank=1,
                                       source_type="client_owned", fetch_status="ok",
                                       present_brands={"client": True, "competitors": []}))
    sqr.sources.append(ScanQuerySource(url="https://slow.example/a", domain="slow.example", rank=2,
                                       source_type="third_party", fetch_status="skipped"))
    db.commit()

    ps.refresh_targets(scan.id, client.id, db)

    assert db.query(PlacementTarget).count() == 0


def test_evidence_reflects_the_latest_scan(db):
    client, rival = _client(db)
    first = _scan(db, client, day=0)
    _answer(db, first, sources=[(*_LIST, False, [])])
    ps.refresh_targets(first.id, client.id, db)

    second = _scan(db, client, day=7)
    _answer(db, second, platform="gemini", category="local", sources=[(*_LIST, False, [str(rival.id)])])
    latest = _answer(db, second, platform="claude", sources=[(*_LIST, False, [])])
    ps.refresh_targets(second.id, client.id, db)

    t = db.query(PlacementTarget).one()
    assert t.answers_count == 2
    assert t.platforms == ["claude", "gemini"]
    assert t.query_categories == ["local", "recommendation"]
    assert t.competitors_present == [str(rival.id)]
    assert t.first_seen_scan_id == first.id and t.last_seen_scan_id == second.id
    # recommendation outranks local as proof: it is the stronger buyer question.
    assert t.representative_result_id == latest.id


def test_representative_answer_is_one_where_the_client_was_not_seen(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    unseen = _answer(db, scan, platform="chatgpt", seen=False, sources=[(*_LIST, False, [])])
    _answer(db, scan, platform="gemini", seen=True, sources=[(*_LIST, False, [])])

    ps.refresh_targets(scan.id, client.id, db)

    assert db.query(PlacementTarget).one().representative_result_id == unseen.id


def test_brand_questions_are_not_used_as_proof_when_a_buyer_question_exists(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    buyer = _answer(db, scan, category="recommendation", sources=[(*_LIST, False, [])])
    _answer(db, scan, category="brand", query="tell me about Acme Dental",
            sources=[(*_LIST, False, [])])

    ps.refresh_targets(scan.id, client.id, db)

    assert db.query(PlacementTarget).one().representative_result_id == buyer.id


def test_target_links_to_a_matching_authority_asset(db):
    client, _ = _client(db)
    asset = AuthorityAsset(client_id=client.id, name="Yellow Pages MY", asset_type="directory",
                           provenance_domain="yellowpages.my")
    db.add(asset)
    db.commit()
    scan = _scan(db, client)
    _answer(db, scan, sources=[("https://www.yellowpages.my/dentists", "www.yellowpages.my",
                                "Dentists", False, [])])

    ps.refresh_targets(scan.id, client.id, db)

    t = db.query(PlacementTarget).one()
    assert t.authority_asset_id == asset.id
    assert t.category == "directory"


def test_target_goes_stale_after_missing_scans_and_reopens(db):
    client, _ = _client(db)
    first = _scan(db, client, day=0)
    _answer(db, first, sources=[(*_LIST, False, [])])
    ps.refresh_targets(first.id, client.id, db)

    other = ("https://other.example/x", "other.example", "Other", False, [])
    for day in (1, 2, 3):
        s = _scan(db, client, day=day)
        _answer(db, s, sources=[other])
        ps.refresh_targets(s.id, client.id, db)

    t = db.query(PlacementTarget).filter_by(url=_LIST[0]).one()
    assert t.status == "stale" and t.scans_missing == 3

    back = _scan(db, client, day=4)
    _answer(db, back, sources=[(*_LIST, False, [])])
    ps.refresh_targets(back.id, client.id, db)
    db.refresh(t)
    assert t.status == "open" and t.scans_missing == 0


def test_a_scan_with_no_checked_sources_does_not_age_targets(db):
    client, _ = _client(db)
    first = _scan(db, client, day=0)
    _answer(db, first, sources=[(*_LIST, False, [])])
    ps.refresh_targets(first.id, client.id, db)

    empty = _scan(db, client, day=1)
    _answer(db, empty)  # enrichment produced nothing usable
    ps.refresh_targets(empty.id, client.id, db)

    assert db.query(PlacementTarget).one().scans_missing == 0


def test_dismissed_target_stays_dismissed_when_seen_again(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    _answer(db, scan, sources=[(*_LIST, False, [])])
    ps.refresh_targets(scan.id, client.id, db)
    t = db.query(PlacementTarget).one()
    t.status = "dismissed"
    db.commit()

    again = _scan(db, client, day=1)
    _answer(db, again, sources=[(*_LIST, False, [])])
    ps.refresh_targets(again.id, client.id, db)

    db.refresh(t)
    assert t.status == "dismissed"


def test_open_target_records_when_the_page_starts_naming_the_client(db):
    client, _ = _client(db)
    scan = _scan(db, client)
    _answer(db, scan, sources=[(*_LIST, False, [])])
    ps.refresh_targets(scan.id, client.id, db)

    later = _scan(db, client, day=1)
    _answer(db, later, sources=[(*_LIST, True, [])])
    ps.refresh_targets(later.id, client.id, db)

    assert db.query(PlacementTarget).one().client_present is True


def test_listicle_title_detection():
    assert ps.categorize("kl-guide.example", "10 Best Dentists in KL (2026)") == "listicle"
    assert ps.categorize("blog.example", "Top 7 dental clinics near Bangsar") == "listicle"
    assert ps.categorize("blog.example", "How to choose a dentist") == "other"
    assert ps.categorize("www.yellowpages.my", "Best dentists") == "directory"
    assert ps.categorize("www.thestar.com.my", "Best dentists in KL") == "listicle"
    assert ps.categorize("www.thestar.com.my", "Clinic opens in Bangsar") == "news"
    assert ps.categorize("moh.gov.my", "Registered clinics") == "reference"
    assert ps.categorize("example.com", None) == "other"


# ── wiring: run after every scan, never able to undo it ─────────────────────

class _FakePlatform:
    platform = "chatgpt"

    def query(self, prompt):
        from app.services.platform_clients.base import PlatformResult
        return PlatformResult(text="Several clinics.", model="m", input_tokens=1, output_tokens=1)


def _run_scan(db, **patches):
    from unittest.mock import patch
    from app.services import scan_service

    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com",
                    industry="dentist", enabled_platforms=["chatgpt"])
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="pending")
    db.add_all([client, scan])
    db.commit()
    with patch.object(scan_service, "get_platform_client", return_value=_FakePlatform()), \
         patch.object(scan_service, "record_llm_usage"), \
         patch.object(scan_service, "extract_position", return_value=None), \
         patch("app.services.remediation_service.sync_remediation_items"), \
         patch("app.services.provenance_service.enrich_scan_sources"), \
         patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0), \
         patch("app.services.placement_service.refresh_targets", **patches) as refresh:
        scan_service.run_scan(scan.id, db)
    db.refresh(scan)
    return scan, client, refresh


def test_scan_refreshes_placement_targets(db):
    scan, client, refresh = _run_scan(db)
    assert scan.status == "completed"
    refresh.assert_called_once_with(scan.id, client.id, db)


def test_placement_refresh_failure_leaves_the_scan_completed(db):
    scan, _, _ = _run_scan(db, side_effect=RuntimeError("boom"))
    assert scan.status == "completed"
