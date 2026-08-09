"""Coverage contract for the dashboard event maps.

Same rationale as frontend nav-icon-coverage.test.ts: a missing map entry is
not a compile error, it is a silently mis-rendered feed row. Every known
activity event type must appear in all three maps; unknown types fall back to
tier "notable" (visible, never swallowed) — that fallback is asserted in
test_dashboard_service.py, not here.
"""
from app.core.constants import (
    DASHBOARD_CATEGORY_LABELS,
    DEFAULT_EVENT_TIER,
    EVENT_CATEGORIES,
    EVENT_LINK_ROUTES,
    EVENT_TIER_ATTENTION,
    EVENT_TIER_NOTABLE,
    EVENT_TIER_ROUTINE,
    EVENT_TIERS,
    KNOWN_ACTIVITY_EVENT_TYPES,
)

VALID_TIERS = {EVENT_TIER_ATTENTION, EVENT_TIER_NOTABLE, EVENT_TIER_ROUTINE}


def test_every_known_event_type_has_a_tier():
    assert set(EVENT_TIERS) == set(KNOWN_ACTIVITY_EVENT_TYPES)
    assert set(EVENT_TIERS.values()) <= VALID_TIERS


def test_every_known_event_type_has_a_category():
    assert set(EVENT_CATEGORIES) == set(KNOWN_ACTIVITY_EVENT_TYPES)
    assert set(EVENT_CATEGORIES.values()) == set(DASHBOARD_CATEGORY_LABELS)


def test_every_known_event_type_has_a_link_route():
    assert set(EVENT_LINK_ROUTES) == set(KNOWN_ACTIVITY_EVENT_TYPES)
    for route in EVENT_LINK_ROUTES.values():
        # "" = client overview; otherwise a client-relative route like "/scan"
        assert route == "" or route.startswith("/")


def test_default_tier_is_notable_not_routine():
    # A forgotten new event type must be visible, not silently swallowed.
    assert DEFAULT_EVENT_TIER == EVENT_TIER_NOTABLE


def test_attention_tier_matches_spec():
    attention = {t for t, tier in EVENT_TIERS.items() if tier == EVENT_TIER_ATTENTION}
    assert attention == {
        "scan_failed", "scan_platform_unavailable", "scan_blocked_budget",
        "hallucination_flagged", "alert_sent", "citation_flip",
    }
