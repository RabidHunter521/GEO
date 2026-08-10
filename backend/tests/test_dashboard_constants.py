"""Coverage contract for the dashboard event maps.

Same rationale as frontend nav-icon-coverage.test.ts: a missing map entry is
not a compile error, it is a silently mis-rendered feed row. Every known
activity event type must appear in all three maps; unknown types fall back to
tier "notable" (visible, never swallowed) — that fallback is asserted in
test_dashboard_service.py, not here.
"""
import ast
from pathlib import Path

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

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# Only live application code — backend/tests/ and backend/scripts/ are
# deliberately excluded (scripts are one-off/seed code, not live writers; this
# test file itself is not a writer). See the constants.py comment above
# KNOWN_ACTIVITY_EVENT_TYPES for why seed-originated types still need manual
# coverage that no static scan can provide.
SCAN_DIRS = (BACKEND_ROOT / "app", BACKEND_ROOT / "workers")


def _string_values(node: ast.AST) -> list[str]:
    """Collect ast.Constant string values from a keyword-argument value node.

    Handles the ternary case (`event_type="a" if cond else "b"`, an
    ast.IfExp) by collecting BOTH branches. Non-literal values (variables,
    f-strings, function calls) are ignored rather than failing — this test
    only asserts about literals it can prove are wrong.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _string_values(node.body) + _string_values(node.orelse)
    return []


def _find_activity_log_event_types(path: Path) -> list[str]:
    """Return every event_type= string literal passed to ActivityLog(...) in path."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `ActivityLog(...)` and `module.ActivityLog(...)`.
        is_activity_log = (
            (isinstance(func, ast.Name) and func.id == "ActivityLog")
            or (isinstance(func, ast.Attribute) and func.attr == "ActivityLog")
        )
        if not is_activity_log:
            continue
        for kw in node.keywords:
            if kw.arg == "event_type":
                found.extend(_string_values(kw.value))
    return found


def test_every_live_activity_log_writer_is_a_known_event_type():
    """Static guard: every event_type literal written by app/ or workers/ code
    must be classified in KNOWN_ACTIVITY_EVENT_TYPES.

    This is the check the four-maps-agree-with-each-other tests above cannot
    provide: it catches a live writer missing from ALL FOUR structures, which
    is exactly how both `content_analyzed`/`roadmap_generated` (grep of
    backend/app/ never looked in backend/workers/) and, earlier,
    `share_link_generated` (hidden inside a ternary a regex missed) got
    through. Uses ast, not regex, specifically to handle that ternary case.
    """
    offenders: dict[str, set[str]] = {}
    for scan_dir in SCAN_DIRS:
        for path in sorted(scan_dir.rglob("*.py")):
            for event_type in _find_activity_log_event_types(path):
                if event_type not in KNOWN_ACTIVITY_EVENT_TYPES:
                    rel = path.relative_to(BACKEND_ROOT)
                    offenders.setdefault(str(rel), set()).add(event_type)

    assert not offenders, (
        "Found ActivityLog(event_type=...) literals not classified in "
        "KNOWN_ACTIVITY_EVENT_TYPES (backend/app/core/constants.py). Add each "
        "one to KNOWN_ACTIVITY_EVENT_TYPES, EVENT_TIERS, EVENT_CATEGORIES, and "
        f"EVENT_LINK_ROUTES. Offenders: {offenders}"
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
