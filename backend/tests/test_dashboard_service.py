from datetime import datetime, timedelta
from datetime import timezone as _tz
from decimal import Decimal

from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.llm_call_log import LlmCallLog
from app.models.scan import Scan
from app.services import dashboard_service
from app.services.dashboard_service import resolve_period


def _client(db, name="Acme", archived=False, prospect=False):
    c = Client(
        name=name, website=f"https://{name.lower()}.example", industry="retail",
        archived_at=utcnow() if archived else None, is_prospect=prospect,
    )
    db.add(c)
    db.commit()
    return c


def _event(db, client, event_type="scan_completed", note="note", days_ago=1):
    e = ActivityLog(
        client_id=client.id, event_type=event_type, note=note,
        created_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(e)
    db.commit()
    return e


def _period(days=30):
    return resolve_period(days, None, None)


def _score(db, client, overall, days_ago):
    # geo_scores requires a scan_id; a minimal scan row satisfies the FK.
    scan = Scan(client_id=client.id)
    db.add(scan)
    db.flush()
    s = GeoScore(
        client_id=client.id, scan_id=scan.id, overall_score=overall,
        computed_at=utcnow() - timedelta(days=days_ago),
    )
    db.add(s)
    db.commit()
    return s


def _cost(db, client, usd, days_ago=1, service="scan_engine"):
    row = LlmCallLog(
        client_id=client.id if client else None,
        service=service, prompt_version="v1", model="claude-sonnet-5",
        input_tokens=10, output_tokens=10, cost_usd=Decimal(str(usd)),
        called_at=datetime.now(_tz.utc) - timedelta(days=days_ago),
    )
    db.add(row)
    db.commit()
    return row


class TestResolvePeriod:
    def test_days_window_is_naive_utc(self):
        p = resolve_period(7, None, None)
        assert p.start.tzinfo is None and p.end.tzinfo is None
        assert (p.end - p.start) == timedelta(days=7)

    def test_explicit_range_is_end_exclusive(self):
        from datetime import date
        p = resolve_period(30, date(2026, 8, 1), date(2026, 8, 3))
        assert p.start == datetime(2026, 8, 1)
        assert p.end == datetime(2026, 8, 4)  # end_date + 1 day, exclusive

    def test_aware_properties_are_utc(self):
        from datetime import timezone
        p = _period()
        assert p.start_aware.tzinfo == timezone.utc
        assert p.start_aware.replace(tzinfo=None) == p.start


class TestFeed:
    def test_orders_newest_first_across_clients(self, db):
        a, b = _client(db, "Alpha"), _client(db, "Beta")
        _event(db, a, days_ago=3)
        newest = _event(db, b, days_ago=1)
        res = dashboard_service.get_feed(db, _period())
        assert [i.id for i in res.items][0] == newest.id
        assert res.total == 2 and res.has_more is False

    def test_includes_client_name_tier_category_and_link(self, db):
        c = _client(db, "Alpha")
        _event(db, c, event_type="hallucination_flagged")
        item = dashboard_service.get_feed(db, _period()).items[0]
        assert item.client_name == "Alpha"
        assert item.tier == "attention"
        assert item.category == "alerts_issues"
        assert item.link_path == f"/clients/{c.id}/scan"

    def test_unknown_event_type_defaults_notable_with_activity_link(self, db):
        c = _client(db)
        _event(db, c, event_type="brand_new_event")
        item = dashboard_service.get_feed(db, _period()).items[0]
        assert item.tier == "notable"
        assert item.category is None
        assert item.link_path == f"/clients/{c.id}/activity"

    def test_excludes_archived_clients(self, db):
        _event(db, _client(db, "Gone", archived=True))
        assert dashboard_service.get_feed(db, _period()).total == 0

    def test_includes_prospects(self, db):
        # Unlike portfolio health, the feed deliberately includes prospects —
        # they are real scanned entities whose events matter operationally.
        lead = _client(db, "Lead", prospect=True)
        _event(db, lead, event_type="scan_completed")
        res = dashboard_service.get_feed(db, _period())
        assert res.total == 1 and res.items[0].client_id == lead.id

    def test_filters_events_outside_the_window(self, db):
        c = _client(db)
        _event(db, c, days_ago=40)  # outside a 30-day window
        _event(db, c, days_ago=5)
        assert dashboard_service.get_feed(db, _period(30)).total == 1

    def test_client_filter(self, db):
        a, b = _client(db, "Alpha"), _client(db, "Beta")
        _event(db, a)
        _event(db, b)
        res = dashboard_service.get_feed(db, _period(), client_id=a.id)
        assert res.total == 1 and res.items[0].client_id == a.id

    def test_category_filter(self, db):
        c = _client(db)
        _event(db, c, event_type="report_sent")
        _event(db, c, event_type="scan_completed")
        res = dashboard_service.get_feed(db, _period(), category="reports_emails")
        assert res.total == 1 and res.items[0].event_type == "report_sent"

    def test_event_type_filter_overrides_category(self, db):
        c = _client(db)
        _event(db, c, event_type="report_sent")
        _event(db, c, event_type="digest_sent")
        res = dashboard_service.get_feed(
            db, _period(), category="reports_emails", event_type="digest_sent"
        )
        assert res.total == 1 and res.items[0].event_type == "digest_sent"

    def test_attention_only_filter(self, db):
        c = _client(db)
        _event(db, c, event_type="scan_failed")
        _event(db, c, event_type="scan_completed")
        res = dashboard_service.get_feed(db, _period(), attention_only=True)
        assert res.total == 1 and res.items[0].event_type == "scan_failed"

    def test_pagination_and_has_more(self, db):
        c = _client(db)
        for i in range(3):
            _event(db, c, days_ago=i + 1)
        first = dashboard_service.get_feed(db, _period(), limit=2, offset=0)
        assert len(first.items) == 2 and first.has_more is True and first.total == 3
        second = dashboard_service.get_feed(db, _period(), limit=2, offset=2)
        assert len(second.items) == 1 and second.has_more is False


class TestSummaryAttention:
    def test_counts_attention_events_in_period(self, db):
        c = _client(db)
        _event(db, c, event_type="scan_failed")
        _event(db, c, event_type="scan_failed", days_ago=40)  # outside window
        _event(db, c, event_type="hallucination_flagged")
        _event(db, c, event_type="citation_flip")
        s = dashboard_service.get_summary(db, _period(30))
        assert s.attention.scans_failed == 1
        assert s.attention.hallucinations_flagged == 1
        assert s.attention.share_of_source_changes == 1
        assert s.attention.alerts_sent == 0
        assert s.attention.platforms_unavailable == 0

    def test_client_filter_scopes_counts(self, db):
        a, b = _client(db, "Alpha"), _client(db, "Beta")
        _event(db, a, event_type="scan_failed")
        _event(db, b, event_type="scan_failed")
        s = dashboard_service.get_summary(db, _period(), client_id=a.id)
        assert s.attention.scans_failed == 1

    def test_counts_scan_blocked_budget_events(self, db):
        # scan_blocked_budget is an attention-tier event (EVENT_TIERS) written
        # by alert_service.py when the spend cap blocks a scan. If the tile
        # doesn't count it, "Nothing needs attention" can be shown while the
        # attention-only feed still has entries.
        c = _client(db)
        _event(db, c, event_type="scan_blocked_budget")
        s = dashboard_service.get_summary(db, _period(30))
        assert s.attention.scans_blocked_budget == 1


class TestSummaryPortfolio:
    def test_average_and_movers(self, db):
        a, b = _client(db, "Alpha"), _client(db, "Beta")
        _score(db, a, 50.0, days_ago=45)  # baseline before window
        _score(db, a, 60.0, days_ago=2)   # +10 → biggest gainer
        _score(db, b, 70.0, days_ago=45)
        _score(db, b, 64.0, days_ago=2)   # -6 → biggest decliner
        p = dashboard_service.get_summary(db, _period(30)).portfolio
        assert p.clients_scored == 2
        assert p.average_score == 62.0        # mean(60, 64)
        assert p.average_delta == 2.0         # mean(+10, -6)
        assert p.biggest_gainer.client_name == "Alpha"
        assert p.biggest_gainer.delta == 10.0
        assert p.biggest_decliner.client_name == "Beta"
        assert p.biggest_decliner.delta == -6.0

    def test_client_without_baseline_contributes_no_delta(self, db):
        a = _client(db, "Alpha")
        _score(db, a, 55.0, days_ago=2)  # no score before window start
        p = dashboard_service.get_summary(db, _period(30)).portfolio
        assert p.average_score == 55.0
        assert p.average_delta is None
        assert p.biggest_gainer is None and p.biggest_decliner is None

    def test_excludes_prospects_and_archived(self, db):
        _score(db, _client(db, "Lead", prospect=True), 90.0, days_ago=2)
        _score(db, _client(db, "Gone", archived=True), 10.0, days_ago=2)
        p = dashboard_service.get_summary(db, _period(30)).portfolio
        assert p.clients_scored == 0 and p.average_score is None

    def test_no_positive_delta_means_no_gainer(self, db):
        a = _client(db, "Alpha")
        _score(db, a, 60.0, days_ago=45)
        _score(db, a, 55.0, days_ago=2)  # only movement is negative
        p = dashboard_service.get_summary(db, _period(30)).portfolio
        assert p.biggest_gainer is None
        assert p.biggest_decliner.delta == -5.0


class TestSummaryCost:
    def test_totals_top_service_and_unattributed(self, db):
        a = _client(db, "Alpha")
        _cost(db, a, "1.50", service="scan_engine")
        _cost(db, a, "0.25", service="digest")
        _cost(db, None, "0.75", service="scan_engine")  # orphaned row
        _cost(db, a, "9.99", days_ago=60)               # outside window
        cost = dashboard_service.get_summary(db, _period(30)).cost
        assert cost.total_cost_usd == 2.50
        assert cost.unattributed_cost_usd == 0.75
        assert cost.top_service.service == "scan_engine"
        assert cost.top_service.cost_usd == 2.25
        assert cost.selected_client_cost_usd is None

    def test_selected_client_share(self, db):
        a, b = _client(db, "Alpha"), _client(db, "Beta")
        _cost(db, a, "1.00")
        _cost(db, b, "3.00")
        cost = dashboard_service.get_summary(db, _period(30), client_id=a.id).cost
        # Total stays portfolio-wide (spec); the share is the scoped figure.
        assert cost.total_cost_usd == 4.00
        assert cost.selected_client_cost_usd == 1.00
