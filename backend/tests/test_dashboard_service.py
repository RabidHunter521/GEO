from datetime import datetime, timedelta

from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client
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

    def test_period_bounds_are_inclusive_start_exclusive_end(self, db):
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
