# Global Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A global `/dashboard` admin page — cross-client activity feed with severity tiers, plus attention/portfolio-health/cost tiles, all driven by URL-param filters — which becomes the app's landing page.

**Architecture:** One read-only backend service (`dashboard_service`) over existing tables (`activity_log`, `geo_scores`, `llm_call_logs`) exposed as two endpoints sharing one filter contract; a Next.js server component reads URL search params and renders a client component for filter interactivity. Event classification (tier/category/route) lives in `app/core/constants.py` with a coverage test.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend), Next.js 15 App Router + shadcn/ui + vitest (frontend), pytest + sqlite (backend tests).

**Spec:** `docs/superpowers/specs/2026-08-09-global-dashboard-design.md` — read it first.

## Global Constraints

- Language rules (CLAUDE.md §2): never render "cited / uncited / citation rate / mentioned" in UI text. `citation_flip` displays as **"Share-of-source change"**. No token counts in UI (dollars only).
- `utcnow()` (app/core/time.py) returns **naive** UTC. Every DateTime column is naive **except `llm_call_logs.called_at` (timezone-aware)**. Never compare naive to aware — derive aware bounds only for `LlmCallLog`.
- Business logic in `app/services/`, never in routes. Routes in `app/api/v1/`. Constants in `app/core/constants.py` — no magic numbers.
- Frontend: shadcn/ui components only; all API calls through `src/lib/api.ts` (SERVER-ONLY — client components go through server actions); types in `src/types/index.ts`; score colors via `getScoreColor()` from `src/lib/score-utils.ts`.
- The dashboard is admin-only. Nothing here may be imported/reachable from `client_view.py` or `/view/[token]` code paths (cost data must never leak).
- Backend tests run via the venv: `./.venv/Scripts/python.exe -m pytest` from `backend/`. Frontend tests: `npx vitest run <file>` from `frontend/`.
- Commit after every task with `rtk git add <files> && rtk git commit -m "..."`.
- Working branch: create `feat/global-dashboard` from master before Task 1 (`rtk git checkout -b feat/global-dashboard`).

---

### Task 1: Event classification constants + coverage test

**Files:**
- Modify: `backend/app/core/constants.py` (append at end)
- Test: `backend/tests/test_dashboard_constants.py` (create)

**Interfaces:**
- Produces (used by Tasks 3–5): `KNOWN_ACTIVITY_EVENT_TYPES: frozenset[str]`, `EVENT_TIERS: dict[str, str]`, `EVENT_CATEGORIES: dict[str, str]`, `EVENT_LINK_ROUTES: dict[str, str]`, `DASHBOARD_CATEGORY_LABELS: dict[str, str]`, `EVENT_TIER_ATTENTION/NOTABLE/ROUTINE: str`, `DEFAULT_EVENT_TIER: str`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dashboard_constants.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_constants.py -v`
Expected: FAIL — `ImportError: cannot import name 'KNOWN_ACTIVITY_EVENT_TYPES'`

- [ ] **Step 3: Append the constants**

Append to `backend/app/core/constants.py`:

```python
# ── Global dashboard event classification ────────────────────────────────────
# Three maps + a canonical set, all keyed by activity_log.event_type. Coverage-
# tested in tests/test_dashboard_constants.py: every known type must appear in
# all three maps. Unknown types (a future writer someone forgets to add here)
# render as DEFAULT_EVENT_TIER / category None / the per-client activity page —
# visible, never silently swallowed. When you add an ActivityLog writer, add
# its event_type to all four structures below.

EVENT_TIER_ATTENTION: Final = "attention"
EVENT_TIER_NOTABLE: Final = "notable"
EVENT_TIER_ROUTINE: Final = "routine"
DEFAULT_EVENT_TIER: Final = EVENT_TIER_NOTABLE

KNOWN_ACTIVITY_EVENT_TYPES: Final = frozenset({
    "alert_sent", "assessment_accepted", "assessment_generated",
    "authority_assets_added", "authority_status_changed", "brief_generated",
    "citation_flip", "client_created", "deliverable_generated",
    "deliverable_reviewed", "digest_sent", "hallucination_flagged",
    "page_audit_run", "report_generated", "report_sent",
    "review_snapshot_added", "scan_blocked_budget", "scan_completed",
    "scan_failed", "scan_platform_unavailable", "share_link_regenerated",
    "share_link_revoked", "site_audit_run", "toolkit_generated",
    "toolkit_verified", "traffic_updated",
})

EVENT_TIERS: Final = {
    # attention — something failed or moved against the client
    "scan_failed": EVENT_TIER_ATTENTION,
    "scan_platform_unavailable": EVENT_TIER_ATTENTION,
    "scan_blocked_budget": EVENT_TIER_ATTENTION,
    "hallucination_flagged": EVENT_TIER_ATTENTION,
    "alert_sent": EVENT_TIER_ATTENTION,
    "citation_flip": EVENT_TIER_ATTENTION,
    # notable — work delivered, or state that changes scores/access
    "client_created": EVENT_TIER_NOTABLE,
    "report_generated": EVENT_TIER_NOTABLE,
    "report_sent": EVENT_TIER_NOTABLE,
    "toolkit_verified": EVENT_TIER_NOTABLE,
    "assessment_generated": EVENT_TIER_NOTABLE,
    "assessment_accepted": EVENT_TIER_NOTABLE,
    "deliverable_generated": EVENT_TIER_NOTABLE,
    "deliverable_reviewed": EVENT_TIER_NOTABLE,
    "brief_generated": EVENT_TIER_NOTABLE,
    "authority_assets_added": EVENT_TIER_NOTABLE,
    "authority_status_changed": EVENT_TIER_NOTABLE,
    "review_snapshot_added": EVENT_TIER_NOTABLE,
    "share_link_regenerated": EVENT_TIER_NOTABLE,
    "share_link_revoked": EVENT_TIER_NOTABLE,
    # routine — the expected heartbeat
    "scan_completed": EVENT_TIER_ROUTINE,
    "digest_sent": EVENT_TIER_ROUTINE,
    "traffic_updated": EVENT_TIER_ROUTINE,
    "toolkit_generated": EVENT_TIER_ROUTINE,
    "page_audit_run": EVENT_TIER_ROUTINE,
    "site_audit_run": EVENT_TIER_ROUTINE,
}

# Category keys are API values (stable identifiers); labels are display text.
DASHBOARD_CATEGORY_LABELS: Final = {
    "scans": "Scans",
    "reports_emails": "Reports & Emails",
    "alerts_issues": "Alerts & Issues",
    "content_work": "Content Work",
    "admin": "Admin",
}

EVENT_CATEGORIES: Final = {
    "scan_completed": "scans",
    "scan_failed": "scans",
    "scan_platform_unavailable": "scans",
    "scan_blocked_budget": "scans",
    "report_generated": "reports_emails",
    "report_sent": "reports_emails",
    "digest_sent": "reports_emails",
    "alert_sent": "alerts_issues",
    "hallucination_flagged": "alerts_issues",
    "citation_flip": "alerts_issues",
    "brief_generated": "content_work",
    "deliverable_generated": "content_work",
    "deliverable_reviewed": "content_work",
    "page_audit_run": "content_work",
    "site_audit_run": "content_work",
    "toolkit_generated": "content_work",
    "toolkit_verified": "content_work",
    "authority_assets_added": "content_work",
    "authority_status_changed": "content_work",
    "review_snapshot_added": "content_work",
    "client_created": "admin",
    "share_link_regenerated": "admin",
    "share_link_revoked": "admin",
    "traffic_updated": "admin",
    "assessment_generated": "admin",
    "assessment_accepted": "admin",
}

# Client-relative route each event links to ("" = the client overview page).
# Deliberately imprecise-but-close (spec: route-by-type, option A) — the
# destination page shows the item within one scroll.
EVENT_LINK_ROUTES: Final = {
    "scan_completed": "/scan",
    "scan_failed": "/scan",
    "scan_platform_unavailable": "/scan",
    "scan_blocked_budget": "/scan",
    "hallucination_flagged": "/scan",
    "citation_flip": "/scan",
    "alert_sent": "",
    "client_created": "",
    "assessment_generated": "",
    "assessment_accepted": "",
    "traffic_updated": "",
    "report_generated": "/reports",
    "report_sent": "/reports",
    "digest_sent": "/activity",
    "toolkit_generated": "/toolkit",
    "toolkit_verified": "/toolkit",
    "site_audit_run": "/toolkit",
    "brief_generated": "/content-roadmap",
    "deliverable_generated": "/content-studio",
    "deliverable_reviewed": "/content-studio",
    "page_audit_run": "/content-studio",
    "authority_assets_added": "/authority",
    "authority_status_changed": "/authority",
    "review_snapshot_added": "/authority",
    "share_link_regenerated": "/settings",
    "share_link_revoked": "/settings",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_constants.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/core/constants.py backend/tests/test_dashboard_constants.py && rtk git commit -m "feat(dashboard): event tier/category/route classification maps"
```

---

### Task 2: Migration — index for the global feed query

**Files:**
- Create: `backend/alembic/versions/b4e8f2a6c9d1_add_activity_created_at_index.py`

**Interfaces:**
- Consumes: current alembic head `e2b8d6a5f1c3` (verified 2026-08-09).
- Produces: index `ix_activity_created_at` on `activity_log(created_at)` — plain btree serves `ORDER BY created_at DESC` via backward scan; the existing composite `ix_activity_client_event_created` leads with `client_id` and cannot serve the all-clients-by-time default.

Follow the `seenby-migrations` skill. No new table → no RLS clause needed.

- [ ] **Step 1: Verify the head and revision-ID uniqueness**

Run (from `backend/`):
```bash
./.venv/Scripts/alembic.exe heads
```
Expected: exactly `e2b8d6a5f1c3 (head)`. If different, use the actual head as `down_revision`.

```bash
grep -r "b4e8f2a6c9d1" alembic/versions/ || echo CLEAR
```
Expected: `CLEAR` (a duplicate revision ID shipped once before in this repo — always check).

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/b4e8f2a6c9d1_add_activity_created_at_index.py`:

```python
"""add_activity_created_at_index

The global dashboard feed reads activity_log across ALL clients ordered by
created_at. The existing composite ix_activity_client_event_created leads
with client_id, so it cannot provide that ordering. A plain btree on
created_at serves ORDER BY created_at DESC via backward index scan.

Revision ID: b4e8f2a6c9d1
Revises: e2b8d6a5f1c3
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b4e8f2a6c9d1'
down_revision: Union[str, None] = 'e2b8d6a5f1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_activity_created_at", "activity_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_activity_created_at", table_name="activity_log")
```

- [ ] **Step 3: Verify the chain is linear with a single head**

```bash
./.venv/Scripts/alembic.exe heads
```
Expected: exactly `b4e8f2a6c9d1 (head)` — one head, no branches.

- [ ] **Step 4: Commit**

```bash
rtk git add backend/alembic/versions/b4e8f2a6c9d1_add_activity_created_at_index.py && rtk git commit -m "feat(dashboard): index activity_log.created_at for the global feed"
```

---

### Task 3: Schemas + dashboard service — period handling and feed

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/services/dashboard_service.py`
- Test: `backend/tests/test_dashboard_service.py` (create; summary tests are added in Task 4)

**Interfaces:**
- Consumes: Task 1 constants; models `ActivityLog`, `Client`.
- Produces (used by Tasks 4–5):
  - `Period` dataclass: naive-UTC `start`/`end` (`[start, end)`), properties `start_aware`/`end_aware` (UTC-aware copies for `LlmCallLog` only).
  - `resolve_period(days: int, start_date: date | None, end_date: date | None) -> Period`
  - `get_feed(db, period, *, client_id=None, category=None, event_type=None, attention_only=False, limit=50, offset=0) -> DashboardFeedResponse`
  - Pydantic models: `DashboardFeedItem`, `DashboardFeedResponse` (fields below).

- [ ] **Step 1: Write the schemas**

Create `backend/app/schemas/dashboard.py`:

```python
"""Global dashboard response shapes. ADMIN-ONLY — never import from
client_view code paths: CostSummary must not be reachable from any
share-token surface."""
import uuid
from datetime import datetime
from pydantic import BaseModel


class DashboardFeedItem(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    event_type: str
    note: str
    created_at: datetime
    tier: str            # attention | notable | routine
    category: str | None  # None for unmapped (future) event types
    link_path: str       # absolute admin path, e.g. /clients/<id>/scan


class DashboardFeedResponse(BaseModel):
    items: list[DashboardFeedItem]
    total: int
    has_more: bool


class AttentionCounts(BaseModel):
    scans_failed: int
    platforms_unavailable: int
    hallucinations_flagged: int
    alerts_sent: int
    share_of_source_changes: int


class DashboardMover(BaseModel):
    client_id: uuid.UUID
    client_name: str
    delta: float
    latest_score: float


class PortfolioHealth(BaseModel):
    average_score: float | None   # None when no active client has a score
    average_delta: float | None   # None when no client has a pre-period baseline
    clients_scored: int
    biggest_gainer: DashboardMover | None   # only when its delta > 0
    biggest_decliner: DashboardMover | None  # only when its delta < 0


class ServiceCost(BaseModel):
    service: str
    cost_usd: float


class CostSummary(BaseModel):
    total_cost_usd: float
    top_service: ServiceCost | None
    unattributed_cost_usd: float          # rows whose client was deleted (SET NULL)
    selected_client_cost_usd: float | None  # only when a client filter is active


class DashboardSummaryResponse(BaseModel):
    attention: AttentionCounts
    portfolio: PortfolioHealth
    cost: CostSummary
```

- [ ] **Step 2: Write the failing feed tests**

Create `backend/tests/test_dashboard_service.py`:

```python
import uuid
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.dashboard_service'`

- [ ] **Step 4: Write the service (period + feed)**

Create `backend/app/services/dashboard_service.py`:

```python
"""Global dashboard reads — cross-client feed + summary tiles.

READ ONLY by design (spec 2026-08-09): the dashboard links out to the pages
where work happens; it never mutates state.

ADMIN-ONLY: cost aggregation lives here. Never import this module from
client_view code paths — nothing on a share-token surface may reach it.

Timezone contract: activity_log.created_at and geo_scores.computed_at are
naive UTC (see app/core/time.utcnow); llm_call_logs.called_at is the one
timezone-aware column. Period carries naive bounds and derives aware copies
strictly for LlmCallLog comparisons — comparing naive to aware is the bug
this design exists to prevent.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.constants import (
    DEFAULT_EVENT_TIER,
    EVENT_CATEGORIES,
    EVENT_LINK_ROUTES,
    EVENT_TIER_ATTENTION,
    EVENT_TIERS,
)
from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.llm_call_log import LlmCallLog
from app.schemas.dashboard import (
    AttentionCounts,
    CostSummary,
    DashboardFeedItem,
    DashboardFeedResponse,
    DashboardMover,
    DashboardSummaryResponse,
    PortfolioHealth,
    ServiceCost,
)


@dataclass(frozen=True)
class Period:
    """Half-open interval [start, end) in naive UTC."""

    start: datetime
    end: datetime

    @property
    def start_aware(self) -> datetime:
        return self.start.replace(tzinfo=timezone.utc)

    @property
    def end_aware(self) -> datetime:
        return self.end.replace(tzinfo=timezone.utc)


def resolve_period(
    days: int, start_date: date | None, end_date: date | None
) -> Period:
    if start_date is not None and end_date is not None:
        # Whole calendar days, end-exclusive: [start 00:00, end+1day 00:00)
        return Period(
            datetime.combine(start_date, dtime.min),
            datetime.combine(end_date + timedelta(days=1), dtime.min),
        )
    now = utcnow()
    return Period(now - timedelta(days=days), now)


def _tier(event_type: str) -> str:
    return EVENT_TIERS.get(event_type, DEFAULT_EVENT_TIER)


def _link_path(client_id: uuid.UUID, event_type: str) -> str:
    # Unknown types fall back to the per-client activity page, which always
    # exists and shows the raw entry.
    route = EVENT_LINK_ROUTES.get(event_type, "/activity")
    return f"/clients/{client_id}{route}"


def get_feed(
    db: Session,
    period: Period,
    *,
    client_id: uuid.UUID | None = None,
    category: str | None = None,
    event_type: str | None = None,
    attention_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> DashboardFeedResponse:
    q = (
        db.query(ActivityLog, Client.name)
        .join(Client, ActivityLog.client_id == Client.id)
        .filter(Client.archived_at.is_(None))
        .filter(
            ActivityLog.created_at >= period.start,
            ActivityLog.created_at < period.end,
        )
    )
    if client_id is not None:
        q = q.filter(ActivityLog.client_id == client_id)
    if event_type:
        q = q.filter(ActivityLog.event_type == event_type)
    elif category:
        types = [t for t, c in EVENT_CATEGORIES.items() if c == category]
        q = q.filter(ActivityLog.event_type.in_(types))
    if attention_only:
        attention = [
            t for t, tier in EVENT_TIERS.items() if tier == EVENT_TIER_ATTENTION
        ]
        q = q.filter(ActivityLog.event_type.in_(attention))

    total = q.count()
    rows = (
        q.order_by(desc(ActivityLog.created_at)).offset(offset).limit(limit).all()
    )
    items = [
        DashboardFeedItem(
            id=entry.id,
            client_id=entry.client_id,
            client_name=name,
            event_type=entry.event_type,
            note=entry.note,
            created_at=entry.created_at,
            tier=_tier(entry.event_type),
            category=EVENT_CATEGORIES.get(entry.event_type),
            link_path=_link_path(entry.client_id, entry.event_type),
        )
        for entry, name in rows
    ]
    return DashboardFeedResponse(
        items=items, total=total, has_more=offset + len(items) < total
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_service.py -v`
Expected: all pass (13 tests)

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/schemas/dashboard.py backend/app/services/dashboard_service.py backend/tests/test_dashboard_service.py && rtk git commit -m "feat(dashboard): feed query with tier/category/link classification"
```

---

### Task 4: Dashboard service — summary (attention, portfolio health, cost)

**Files:**
- Modify: `backend/app/services/dashboard_service.py` (append)
- Test: `backend/tests/test_dashboard_service.py` (append)

**Interfaces:**
- Consumes: `Period`, Task 3 schemas, models `GeoScore`, `LlmCallLog`.
- Produces (used by Task 5): `get_summary(db, period, *, client_id=None) -> DashboardSummaryResponse`.

- [ ] **Step 1: Write the failing summary tests**

Append to `backend/tests/test_dashboard_service.py`:

```python
from datetime import timezone as _tz
from decimal import Decimal

from app.models.geo_score import GeoScore
from app.models.llm_call_log import LlmCallLog
from app.models.scan import Scan


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_service.py -k Summary -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_summary'`

If `Scan(client_id=...)` fails because `scans` has other non-nullable columns, open `backend/app/models/scan.py` and fill the minimal required fields in `_score` (keep the helper the single place that knows this).

- [ ] **Step 3: Implement the summary**

Append to `backend/app/services/dashboard_service.py`:

```python
_ATTENTION_FIELD_BY_EVENT = {
    "scan_failed": "scans_failed",
    "scan_platform_unavailable": "platforms_unavailable",
    "hallucination_flagged": "hallucinations_flagged",
    "alert_sent": "alerts_sent",
    "citation_flip": "share_of_source_changes",
}


def get_summary(
    db: Session, period: Period, *, client_id: uuid.UUID | None = None
) -> DashboardSummaryResponse:
    return DashboardSummaryResponse(
        attention=_attention_counts(db, period, client_id),
        portfolio=_portfolio_health(db, period, client_id),
        cost=_cost_summary(db, period, client_id),
    )


def _attention_counts(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> AttentionCounts:
    q = (
        db.query(ActivityLog.event_type, func.count(ActivityLog.id))
        .join(Client, ActivityLog.client_id == Client.id)
        .filter(Client.archived_at.is_(None))
        .filter(
            ActivityLog.created_at >= period.start,
            ActivityLog.created_at < period.end,
            ActivityLog.event_type.in_(_ATTENTION_FIELD_BY_EVENT),
        )
        .group_by(ActivityLog.event_type)
    )
    if client_id is not None:
        q = q.filter(ActivityLog.client_id == client_id)
    counts = dict(q.all())
    return AttentionCounts(
        **{
            field: counts.get(event, 0)
            for event, field in _ATTENTION_FIELD_BY_EVENT.items()
        }
    )


def _portfolio_health(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> PortfolioHealth:
    clients_q = db.query(Client).filter(
        Client.archived_at.is_(None), Client.is_prospect.is_(False)
    )
    if client_id is not None:
        clients_q = clients_q.filter(Client.id == client_id)
    clients = clients_q.all()
    name_by_id = {c.id: c.name for c in clients}
    if not clients:
        return PortfolioHealth(
            average_score=None, average_delta=None, clients_scored=0,
            biggest_gainer=None, biggest_decliner=None,
        )

    # One pass over scores, newest first: the first row seen per client is
    # its latest (≤ period end); the first row with computed_at < start is
    # its baseline. Clients with no baseline contribute no delta (spec).
    scores = (
        db.query(GeoScore)
        .filter(
            GeoScore.client_id.in_(name_by_id),
            GeoScore.computed_at < period.end,
        )
        .order_by(GeoScore.client_id, desc(GeoScore.computed_at))
        .all()
    )
    latest: dict[uuid.UUID, float] = {}
    baseline: dict[uuid.UUID, float] = {}
    for s in scores:
        if s.client_id not in latest:
            latest[s.client_id] = s.overall_score
        if s.client_id not in baseline and s.computed_at < period.start:
            baseline[s.client_id] = s.overall_score

    if not latest:
        return PortfolioHealth(
            average_score=None, average_delta=None, clients_scored=0,
            biggest_gainer=None, biggest_decliner=None,
        )

    deltas = {
        cid: latest[cid] - baseline[cid] for cid in latest if cid in baseline
    }

    def _mover(cid: uuid.UUID) -> DashboardMover:
        return DashboardMover(
            client_id=cid, client_name=name_by_id[cid],
            delta=round(deltas[cid], 1), latest_score=latest[cid],
        )

    gainer_id = max(deltas, key=deltas.__getitem__, default=None)
    decliner_id = min(deltas, key=deltas.__getitem__, default=None)
    return PortfolioHealth(
        average_score=round(sum(latest.values()) / len(latest), 1),
        average_delta=(
            round(sum(deltas.values()) / len(deltas), 1) if deltas else None
        ),
        clients_scored=len(latest),
        biggest_gainer=(
            _mover(gainer_id) if gainer_id is not None and deltas[gainer_id] > 0 else None
        ),
        biggest_decliner=(
            _mover(decliner_id) if decliner_id is not None and deltas[decliner_id] < 0 else None
        ),
    )


def _cost_summary(
    db: Session, period: Period, client_id: uuid.UUID | None
) -> CostSummary:
    # llm_call_logs.called_at is the one AWARE column — aware bounds only here.
    in_period = [
        LlmCallLog.called_at >= period.start_aware,
        LlmCallLog.called_at < period.end_aware,
    ]
    total = (
        db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
        .filter(*in_period)
        .scalar()
    )
    unattributed = (
        db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
        .filter(*in_period, LlmCallLog.client_id.is_(None))
        .scalar()
    )
    top = (
        db.query(
            LlmCallLog.service,
            func.sum(LlmCallLog.cost_usd).label("cost"),
        )
        .filter(*in_period)
        .group_by(LlmCallLog.service)
        .order_by(func.sum(LlmCallLog.cost_usd).desc())
        .first()
    )
    selected = None
    if client_id is not None:
        selected = float(
            db.query(func.coalesce(func.sum(LlmCallLog.cost_usd), 0))
            .filter(*in_period, LlmCallLog.client_id == client_id)
            .scalar()
        )
    return CostSummary(
        total_cost_usd=float(total),
        top_service=(
            ServiceCost(service=top.service, cost_usd=float(top.cost))
            if top is not None
            else None
        ),
        unattributed_cost_usd=float(unattributed),
        selected_client_cost_usd=selected,
    )
```

- [ ] **Step 4: Run the full service test file**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_dashboard_service.py -v`
Expected: all pass (22 tests)

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/dashboard_service.py backend/tests/test_dashboard_service.py && rtk git commit -m "feat(dashboard): summary tiles — attention counts, portfolio health, cost"
```

---

### Task 5: API routes + router registration

**Files:**
- Create: `backend/app/api/v1/dashboard.py`
- Modify: `backend/app/api/v1/router.py` (import + include)
- Test: `backend/tests/test_api_dashboard.py` (create)

**Interfaces:**
- Consumes: `dashboard_service.resolve_period/get_feed/get_summary`, `DASHBOARD_CATEGORY_LABELS`.
- Produces (used by Task 6): `GET /api/v1/dashboard/summary` and `GET /api/v1/dashboard/feed`, query params: `days` (int, default 30, 1–365), `start_date`/`end_date` (ISO dates, both or neither, override `days`), `client_id` (uuid), and for feed only `category`, `event_type`, `attention_only` (bool), `limit` (default 50, max 200), `offset`.

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_api_dashboard.py`:

```python
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient as HttpClient

from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client


def _make_app(db):
    from app.main import app
    from app.core.auth import require_api_key
    from app.core.database import get_db

    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    return app


def _seed(db):
    c = Client(name="Acme", website="https://acme.example", industry="retail")
    db.add(c)
    db.commit()
    db.add(ActivityLog(
        client_id=c.id, event_type="scan_failed", note="Scan failed",
        created_at=utcnow() - timedelta(days=1),
    ))
    db.commit()
    return c


def test_feed_requires_auth():
    from app.main import app
    app.dependency_overrides.clear()
    resp = HttpClient(app).get("/api/v1/dashboard/feed")
    assert resp.status_code == 401


def test_summary_requires_auth():
    from app.main import app
    app.dependency_overrides.clear()
    resp = HttpClient(app).get("/api/v1/dashboard/summary")
    assert resp.status_code == 401


def test_feed_returns_classified_items(db):
    c = _seed(db)
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1 and body["has_more"] is False
    item = body["items"][0]
    assert item["client_name"] == "Acme"
    assert item["tier"] == "attention"
    assert item["link_path"] == f"/clients/{c.id}/scan"


def test_summary_shape(db):
    _seed(db)
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/summary")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["attention"]["scans_failed"] == 1
    assert set(body) == {"attention", "portfolio", "cost"}


def test_unknown_category_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed?category=nonsense")
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_half_open_date_range_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get("/api/v1/dashboard/feed?start_date=2026-08-01")
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_reversed_date_range_is_422(db):
    app = _make_app(db)
    resp = HttpClient(app).get(
        "/api/v1/dashboard/feed?start_date=2026-08-05&end_date=2026-08-01"
    )
    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_client_filter_passes_through(db):
    _seed(db)
    app = _make_app(db)
    other = uuid.uuid4()
    resp = HttpClient(app).get(f"/api/v1/dashboard/feed?client_id={other}")
    app.dependency_overrides.clear()
    assert resp.status_code == 200 and resp.json()["total"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_dashboard.py -v`
Expected: FAIL — 404s (route not registered)

- [ ] **Step 3: Write the route module**

Create `backend/app/api/v1/dashboard.py`:

```python
"""Global dashboard — admin-only reads (feed + summary tiles).

Thin routes: all logic in app/services/dashboard_service.py. Never mount or
reuse these from client_view — the cost figures must not be reachable from
any share-token surface (spec: admin-only by construction).
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import DASHBOARD_CATEGORY_LABELS
from app.core.database import get_db
from app.schemas.dashboard import DashboardFeedResponse, DashboardSummaryResponse
from app.services import dashboard_service
from app.services.dashboard_service import Period

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _period(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = None,
    end_date: date | None = None,
) -> Period:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date and end_date must be provided together",
        )
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(
            status_code=422, detail="end_date must be on or after start_date"
        )
    return dashboard_service.resolve_period(days, start_date, end_date)


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    dependencies=[Depends(require_api_key)],
)
def get_summary(
    period: Period = Depends(_period),
    client_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    return dashboard_service.get_summary(db, period, client_id=client_id)


@router.get(
    "/feed",
    response_model=DashboardFeedResponse,
    dependencies=[Depends(require_api_key)],
)
def get_feed(
    period: Period = Depends(_period),
    client_id: uuid.UUID | None = None,
    category: str | None = None,
    event_type: str | None = None,
    attention_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if category is not None and category not in DASHBOARD_CATEGORY_LABELS:
        raise HTTPException(status_code=422, detail="Unknown category")
    return dashboard_service.get_feed(
        db,
        period,
        client_id=client_id,
        category=category,
        event_type=event_type,
        attention_only=attention_only,
        limit=limit,
        offset=offset,
    )
```

- [ ] **Step 4: Register the router**

In `backend/app/api/v1/router.py`: add `dashboard` to the line-2 import list, and add `router.include_router(dashboard.router)` after the `market_intelligence` include.

- [ ] **Step 5: Run the API tests, then the full backend suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_api_dashboard.py -v`
Expected: 8 passed

Run: `./.venv/Scripts/python.exe -m pytest`
Expected: no regressions (baseline was ~807+ green before this branch).

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/api/v1/dashboard.py backend/app/api/v1/router.py backend/tests/test_api_dashboard.py && rtk git commit -m "feat(dashboard): /api/v1/dashboard summary + feed endpoints"
```

---

### Task 6: Frontend types, API client functions, server action

**Files:**
- Modify: `frontend/src/types/index.ts` (append)
- Modify: `frontend/src/lib/api.ts` (append section + extend the type import)
- Create: `frontend/src/app/(admin)/dashboard/actions.ts`

**Interfaces:**
- Consumes: Task 5 endpoints.
- Produces (used by Task 7): types `DashboardEventTier`, `DashboardFeedItem`, `DashboardFeedResponse`, `DashboardSummary`, `DashboardFilters`; functions `getDashboardSummary(filters)`, `getDashboardFeed(filters, offset?)`; server action `loadMoreFeedAction(filters, offset)`.

- [ ] **Step 1: Append types**

Append to `frontend/src/types/index.ts`:

```ts
// ── Global dashboard ─────────────────────────────────────────────────────────

export type DashboardEventTier = "attention" | "notable" | "routine"

export interface DashboardFeedItem {
  id: string
  client_id: string
  client_name: string
  event_type: string
  note: string
  created_at: string
  tier: DashboardEventTier
  category: string | null
  link_path: string
}

export interface DashboardFeedResponse {
  items: DashboardFeedItem[]
  total: number
  has_more: boolean
}

export interface DashboardMover {
  client_id: string
  client_name: string
  delta: number
  latest_score: number
}

export interface DashboardSummary {
  attention: {
    scans_failed: number
    platforms_unavailable: number
    hallucinations_flagged: number
    alerts_sent: number
    share_of_source_changes: number
  }
  portfolio: {
    average_score: number | null
    average_delta: number | null
    clients_scored: number
    biggest_gainer: DashboardMover | null
    biggest_decliner: DashboardMover | null
  }
  cost: {
    total_cost_usd: number
    top_service: { service: string; cost_usd: number } | null
    unattributed_cost_usd: number
    selected_client_cost_usd: number | null
  }
}

/** Filter contract shared by the page URL, api.ts, and the server action. */
export interface DashboardFilters {
  days?: number
  startDate?: string // ISO date; must travel with endDate
  endDate?: string
  clientId?: string
  category?: string
  eventType?: string
  attentionOnly?: boolean
}
```

- [ ] **Step 2: Append API functions**

In `frontend/src/lib/api.ts`: add `DashboardFeedResponse, DashboardFilters, DashboardSummary` to the type-import list on line 4, then append:

```ts
// ── Global dashboard ─────────────────────────────────────────────────────────

function dashboardQuery(f: DashboardFilters, extra?: Record<string, string>): string {
  const p = new URLSearchParams()
  if (f.startDate && f.endDate) {
    p.set("start_date", f.startDate)
    p.set("end_date", f.endDate)
  } else {
    p.set("days", String(f.days ?? 30))
  }
  if (f.clientId) p.set("client_id", f.clientId)
  if (f.category) p.set("category", f.category)
  if (f.eventType) p.set("event_type", f.eventType)
  if (f.attentionOnly) p.set("attention_only", "true")
  for (const [k, v] of Object.entries(extra ?? {})) p.set(k, v)
  return p.toString()
}

export function getDashboardSummary(filters: DashboardFilters): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>(`/api/v1/dashboard/summary?${dashboardQuery(filters)}`)
}

export function getDashboardFeed(
  filters: DashboardFilters,
  offset = 0,
): Promise<DashboardFeedResponse> {
  return apiFetch<DashboardFeedResponse>(
    `/api/v1/dashboard/feed?${dashboardQuery(filters, { offset: String(offset), limit: "50" })}`,
  )
}
```

- [ ] **Step 3: Create the server action**

Create `frontend/src/app/(admin)/dashboard/actions.ts`:

```ts
"use server"
// api.ts is server-only (holds ADMIN_API_KEY); this action is how the client
// component paginates without ever seeing the key.
import { getDashboardFeed } from "@/lib/api"
import type { DashboardFeedResponse, DashboardFilters } from "@/types"

export async function loadMoreFeedAction(
  filters: DashboardFilters,
  offset: number,
): Promise<DashboardFeedResponse> {
  return getDashboardFeed(filters, offset)
}
```

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `rtk npm run typecheck`
Expected: clean

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/types/index.ts frontend/src/lib/api.ts "frontend/src/app/(admin)/dashboard/actions.ts" && rtk git commit -m "feat(dashboard): frontend types, API client, load-more action"
```

---

### Task 7: Dashboard page + client component

**Files:**
- Create: `frontend/src/app/(admin)/dashboard/page.tsx`
- Create: `frontend/src/app/(admin)/dashboard/DashboardClient.tsx`

**Interfaces:**
- Consumes: Task 6 types/functions/action; shadcn `card`, `badge`, `button`, `input`, `select`; `SearchableSelect`; `getScoreColor` from `@/lib/score-utils`.
- Produces: `/dashboard` URL contract (used by Task 8 links): `days`, `start`, `end`, `client`, `category`, `event`, `attention` search params.

**Before writing JSX:** open `frontend/src/components/ui/select.tsx` and confirm the exported names (expected shadcn standard: `Select`, `SelectContent`, `SelectItem`, `SelectTrigger`, `SelectValue`). If the file exports something else, adapt the imports below.

- [ ] **Step 1: Write the server component**

Create `frontend/src/app/(admin)/dashboard/page.tsx`:

```tsx
// frontend/src/app/(admin)/dashboard/page.tsx
// Global dashboard — everything happening across the agency. Server
// component: filters live in the URL so views are bookmarkable and the
// data fetch happens server-side (api.ts is server-only).
import { getClients, getDashboardFeed, getDashboardSummary } from "@/lib/api"
import type { DashboardFilters } from "@/types"
import { DashboardClient } from "./DashboardClient"

export const dynamic = "force-dynamic"

type SearchParams = Record<string, string | string[] | undefined>

function parseFilters(sp: SearchParams): DashboardFilters {
  const s = (k: string) => (typeof sp[k] === "string" ? (sp[k] as string) : undefined)
  const rawDays = Number(s("days") ?? "30")
  return {
    days: Number.isInteger(rawDays) && rawDays >= 1 && rawDays <= 365 ? rawDays : 30,
    startDate: s("start"),
    endDate: s("end"),
    clientId: s("client"),
    category: s("category"),
    eventType: s("event"),
    attentionOnly: s("attention") === "1",
  }
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams
  const filters = parseFilters(sp)
  const [summary, feed, clients] = await Promise.all([
    getDashboardSummary(filters),
    getDashboardFeed(filters),
    getClients(),
  ])
  return (
    <DashboardClient
      // Remount on any filter change so feed pagination state resets.
      key={JSON.stringify(filters)}
      filters={filters}
      summary={summary}
      initialFeed={feed}
      clients={clients.map((c) => ({ id: c.id, name: c.name }))}
    />
  )
}
```

- [ ] **Step 2: Write the client component**

Create `frontend/src/app/(admin)/dashboard/DashboardClient.tsx`:

```tsx
"use client"

import { useState, useTransition } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { AlertTriangle, ArrowDownRight, ArrowUpRight, DollarSign } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { SearchableSelect } from "@/components/ui/searchable-select"
import { getScoreColor } from "@/lib/score-utils"
import { cn } from "@/lib/utils"
import type {
  DashboardEventTier,
  DashboardFeedItem,
  DashboardFeedResponse,
  DashboardFilters,
  DashboardSummary,
} from "@/types"
import { loadMoreFeedAction } from "./actions"

const ALL_CLIENTS = "All clients"

const CATEGORY_OPTIONS = [
  { value: "scans", label: "Scans" },
  { value: "reports_emails", label: "Reports & Emails" },
  { value: "alerts_issues", label: "Alerts & Issues" },
  { value: "content_work", label: "Content Work" },
  { value: "admin", label: "Admin" },
] as const

// Language rules (CLAUDE.md §2): citation_flip must NEVER surface as
// "citation" anything. Other types fall back to a humanized form.
const EVENT_LABELS: Record<string, string> = {
  citation_flip: "Share-of-source change",
  hallucination_flagged: "Accuracy issue flagged",
  scan_blocked_budget: "Scan blocked (budget)",
}

function eventLabel(eventType: string): string {
  if (EVENT_LABELS[eventType]) return EVENT_LABELS[eventType]
  const words = eventType.replace(/_/g, " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const TIER_ROW_STYLES: Record<DashboardEventTier, string> = {
  attention: "border-l-2 border-l-destructive",
  notable: "",
  routine: "opacity-70",
}

const TIER_BADGE_VARIANT: Record<
  DashboardEventTier,
  "destructive" | "secondary" | "outline"
> = {
  attention: "destructive",
  notable: "secondary",
  routine: "outline",
}

const SCORE_TEXT: Record<ReturnType<typeof getScoreColor>, string> = {
  green: "text-emerald-600",
  yellow: "text-amber-600",
  red: "text-red-600",
}

// Backend timestamps are naive UTC with no zone suffix; without the "Z" the
// browser would parse them as local time and shift everything by +8h.
function formatUtc(ts: string): string {
  const iso = ts.endsWith("Z") || ts.includes("+") ? ts : `${ts}Z`
  return new Intl.DateTimeFormat("en-MY", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso))
}

function usd(n: number): string {
  return `$${n.toFixed(2)}`
}

interface Props {
  filters: DashboardFilters
  summary: DashboardSummary
  initialFeed: DashboardFeedResponse
  clients: { id: string; name: string }[]
}

export function DashboardClient({ filters, summary, initialFeed, clients }: Props) {
  const router = useRouter()
  const [items, setItems] = useState<DashboardFeedItem[]>(initialFeed.items)
  const [hasMore, setHasMore] = useState(initialFeed.has_more)
  const [customOpen, setCustomOpen] = useState(Boolean(filters.startDate))
  const [customStart, setCustomStart] = useState(filters.startDate ?? "")
  const [customEnd, setCustomEnd] = useState(filters.endDate ?? "")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function push(next: DashboardFilters) {
    const p = new URLSearchParams()
    if (next.startDate && next.endDate) {
      p.set("start", next.startDate)
      p.set("end", next.endDate)
    } else if (next.days && next.days !== 30) {
      p.set("days", String(next.days))
    }
    if (next.clientId) p.set("client", next.clientId)
    if (next.category) p.set("category", next.category)
    if (next.eventType) p.set("event", next.eventType)
    if (next.attentionOnly) p.set("attention", "1")
    const qs = p.toString()
    startTransition(() => router.push(qs ? `/dashboard?${qs}` : "/dashboard"))
  }

  function onPeriodChange(value: string) {
    if (value === "custom") {
      setCustomOpen(true)
      return
    }
    setCustomOpen(false)
    push({ ...filters, days: Number(value), startDate: undefined, endDate: undefined })
  }

  function applyCustomRange() {
    if (!customStart || !customEnd || customEnd < customStart) return
    push({ ...filters, startDate: customStart, endDate: customEnd })
  }

  function onClientChange(name: string) {
    const client = clients.find((c) => c.name === name)
    push({ ...filters, clientId: client?.id })
  }

  async function loadMore() {
    setLoadError(null)
    try {
      const next = await loadMoreFeedAction(filters, items.length)
      setItems((prev) => [...prev, ...next.items])
      setHasMore(next.has_more)
    } catch {
      setLoadError("Could not load more events. Try again.")
    }
  }

  // Tile links preserve the current period/client, swap the feed slice.
  function eventFilterHref(eventType: string): string {
    const p = new URLSearchParams()
    if (filters.startDate && filters.endDate) {
      p.set("start", filters.startDate)
      p.set("end", filters.endDate)
    } else if (filters.days && filters.days !== 30) {
      p.set("days", String(filters.days))
    }
    if (filters.clientId) p.set("client", filters.clientId)
    p.set("event", eventType)
    return `/dashboard?${p.toString()}`
  }

  const selectedClientName =
    clients.find((c) => c.id === filters.clientId)?.name ?? ALL_CLIENTS
  const periodValue = filters.startDate ? "custom" : String(filters.days ?? 30)
  const { attention, portfolio, cost } = summary

  const attentionRows: { label: string; count: number; event: string }[] = [
    { label: "Scans failed", count: attention.scans_failed, event: "scan_failed" },
    { label: "Platforms unavailable", count: attention.platforms_unavailable, event: "scan_platform_unavailable" },
    { label: "Accuracy issues", count: attention.hallucinations_flagged, event: "hallucination_flagged" },
    { label: "Alerts sent", count: attention.alerts_sent, event: "alert_sent" },
    { label: "Share-of-source changes", count: attention.share_of_source_changes, event: "citation_flip" },
  ]
  const totalAttention = attentionRows.reduce((sum, r) => sum + r.count, 0)

  return (
    <div className={cn("space-y-6", isPending && "pointer-events-none opacity-60")}>
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything happening across your clients. Filters drive the whole page.
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-40">
          <Select value={periodValue} onValueChange={onPeriodChange}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
              <SelectItem value="custom">Custom range</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {customOpen && (
          <div className="flex items-end gap-2">
            <Input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="w-40"
              aria-label="Start date"
            />
            <Input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="w-40"
              aria-label="End date"
            />
            <Button variant="secondary" size="sm" onClick={applyCustomRange}>
              Apply
            </Button>
          </div>
        )}
        <div className="w-56">
          <SearchableSelect
            options={[ALL_CLIENTS, ...clients.map((c) => c.name)]}
            value={selectedClientName}
            onChange={onClientChange}
          />
        </div>
        <div className="w-48">
          <Select
            value={filters.category ?? "all"}
            onValueChange={(v) =>
              push({ ...filters, category: v === "all" ? undefined : v, eventType: undefined })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {CATEGORY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          variant={filters.attentionOnly ? "default" : "outline"}
          size="sm"
          onClick={() => push({ ...filters, attentionOnly: !filters.attentionOnly })}
        >
          <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
          Attention only
        </Button>
        {filters.eventType && (
          <Badge variant="secondary" className="gap-1">
            {eventLabel(filters.eventType)}
            <button
              aria-label="Clear event filter"
              onClick={() => push({ ...filters, eventType: undefined })}
              className="ml-1 font-bold"
            >
              ×
            </button>
          </Badge>
        )}
      </div>

      {/* Stats strip */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Needs attention
            </CardTitle>
          </CardHeader>
          <CardContent>
            {totalAttention === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing needs attention in this period.</p>
            ) : (
              <ul className="space-y-1">
                {attentionRows
                  .filter((r) => r.count > 0)
                  .map((r) => (
                    <li key={r.event}>
                      <Link
                        href={eventFilterHref(r.event)}
                        className="flex items-center justify-between text-sm hover:underline"
                      >
                        <span>{r.label}</span>
                        <span className="font-semibold text-destructive">{r.count}</span>
                      </Link>
                    </li>
                  ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Portfolio health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {portfolio.average_score === null ? (
              <p className="text-sm text-muted-foreground">No scans in this period yet.</p>
            ) : (
              <>
                <p className="text-2xl font-bold">
                  <span className={SCORE_TEXT[getScoreColor(portfolio.average_score)]}>
                    {portfolio.average_score}
                  </span>{" "}
                  <span className="text-sm font-normal text-muted-foreground">
                    avg Growth Readiness · {portfolio.clients_scored} client
                    {portfolio.clients_scored === 1 ? "" : "s"}
                  </span>
                </p>
                {portfolio.average_delta !== null && (
                  <p className="text-sm text-muted-foreground">
                    {portfolio.average_delta >= 0 ? "+" : ""}
                    {portfolio.average_delta} avg movement this period
                  </p>
                )}
                {portfolio.biggest_gainer && (
                  <p className="flex items-center gap-1 text-sm">
                    <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600" />
                    <Link href={`/clients/${portfolio.biggest_gainer.client_id}`} className="hover:underline">
                      {portfolio.biggest_gainer.client_name}
                    </Link>
                    <span className="text-emerald-600">+{portfolio.biggest_gainer.delta}</span>
                  </p>
                )}
                {portfolio.biggest_decliner && (
                  <p className="flex items-center gap-1 text-sm">
                    <ArrowDownRight className="h-3.5 w-3.5 text-red-600" />
                    <Link href={`/clients/${portfolio.biggest_decliner.client_id}`} className="hover:underline">
                      {portfolio.biggest_decliner.client_name}
                    </Link>
                    <span className="text-red-600">{portfolio.biggest_decliner.delta}</span>
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              LLM cost
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            <p className="flex items-center gap-1 text-2xl font-bold">
              <DollarSign className="h-5 w-5 text-muted-foreground" />
              {usd(cost.total_cost_usd)}
            </p>
            {cost.top_service && (
              <p className="text-sm text-muted-foreground">
                Top service: {cost.top_service.service} ({usd(cost.top_service.cost_usd)})
              </p>
            )}
            {cost.selected_client_cost_usd !== null && (
              <p className="text-sm text-muted-foreground">
                {selectedClientName}: {usd(cost.selected_client_cost_usd)}
              </p>
            )}
            {cost.unattributed_cost_usd > 0 && (
              <p className="text-sm text-muted-foreground">
                Unattributed: {usd(cost.unattributed_cost_usd)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Feed */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Activity ({initialFeed.total})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No events match these filters.
            </p>
          ) : (
            <ul className="divide-y divide-border/60">
              {items.map((item) => (
                <li key={item.id}>
                  <Link
                    href={item.link_path}
                    className={cn(
                      "flex items-start gap-3 px-2 py-2.5 transition-colors hover:bg-accent/50",
                      TIER_ROW_STYLES[item.tier],
                    )}
                  >
                    <Badge variant={TIER_BADGE_VARIANT[item.tier]} className="mt-0.5 shrink-0">
                      {eventLabel(item.event_type)}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{item.note}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {item.client_name} · {formatUtc(item.created_at)}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {loadError && <p className="mt-3 text-sm text-destructive">{loadError}</p>}
          {hasMore && (
            <div className="mt-4 text-center">
              <Button variant="outline" size="sm" onClick={loadMore}>
                Load more
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 3: Typecheck and build**

Run (from `frontend/`): `rtk npm run typecheck`
Expected: clean. Fix any shadcn export-name mismatches surfaced here.

Run: `rtk next build`
Expected: `/dashboard` appears in the route list, build succeeds.

- [ ] **Step 4: Commit**

```bash
rtk git add "frontend/src/app/(admin)/dashboard/page.tsx" "frontend/src/app/(admin)/dashboard/DashboardClient.tsx" && rtk git commit -m "feat(dashboard): /dashboard page — filter bar, tiles, tiered feed"
```

---

### Task 8: Nav entry, icon, home redirect, CLAUDE.md §9

**Files:**
- Modify: `frontend/src/lib/navigation.ts` (ADMIN_GLOBAL_NAV)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (icon import + GLOBAL_NAV_ICONS + Brand href)
- Modify: `frontend/src/app/page.tsx` (root redirect)
- Modify: `CLAUDE.md` §9
- Test: existing `frontend/src/lib/__tests__/nav-icon-coverage.test.ts` (no change — must pass)

**Interfaces:**
- Consumes: `/dashboard` route from Task 7.

- [ ] **Step 1: Add the nav item**

In `frontend/src/lib/navigation.ts`, add as the FIRST entry of `ADMIN_GLOBAL_NAV`:

```ts
export const ADMIN_GLOBAL_NAV: readonly NavItem[] = [
  // Landing page: the cross-client "what happened" view. LayoutDashboard is
  // taken by the per-client Overview item — Sidebar uses Radar here.
  { href: "/dashboard", label: "Dashboard" },
  { href: "/clients", label: "All Clients" },
  { href: "/gap-matrix", label: "Portfolio Intelligence" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/review-queue", label: "Review Queue" },
] as const
```

- [ ] **Step 2: Add the icon and repoint the logo**

In `frontend/src/components/layout/Sidebar.tsx`:
1. Add `Radar` to the lucide-react import list (line 9–32).
2. Add to `GLOBAL_NAV_ICONS` (keep insertion order matching nav order):

```ts
export const GLOBAL_NAV_ICONS: Record<string, IconType> = {
  "/dashboard": Radar,
  "/clients": Users,
  "/gap-matrix": Table2,
  "/benchmarks": Gauge,
  "/review-queue": Inbox,
}
```

3. In `Brand()`, change `href="/clients"` to `href="/dashboard"`.

- [ ] **Step 3: Repoint the root redirect**

In `frontend/src/app/page.tsx`, change `redirect("/clients")` to `redirect("/dashboard")` (keep the CSP comment and `dynamic = "force-dynamic"` untouched).

- [ ] **Step 4: Check middleware doesn't gate by path list**

Run: `rtk grep -n "clients" frontend/src/middleware.ts`
If the middleware matcher enumerates admin paths, add `/dashboard`; if it protects everything except `/view` and `/auth` (expected), no change.

- [ ] **Step 5: Run the nav coverage test and typecheck**

Run (from `frontend/`): `npx vitest run src/lib/__tests__/nav-icon-coverage.test.ts`
Expected: 3 passed (missing icon or stale entry would fail here)

Run: `rtk npm run typecheck`
Expected: clean

- [ ] **Step 6: Amend CLAUDE.md §9**

In `CLAUDE.md` section 9, change:

```
/                        → redirect to /clients
```
to:
```
/                        → redirect to /dashboard
/dashboard               → global activity dashboard (feed + attention/health/cost tiles, landing page)
```

- [ ] **Step 7: Commit**

```bash
rtk git add frontend/src/lib/navigation.ts frontend/src/components/layout/Sidebar.tsx frontend/src/app/page.tsx CLAUDE.md && rtk git commit -m "feat(dashboard): nav entry, Radar icon, /dashboard becomes home"
```

---

### Task 9: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run the seenby-verify skill**

Invoke the `seenby-verify` project skill and complete every check it defines: full backend suite via the venv, frontend typecheck + build, banned-language scan, migration sanity (`alembic heads` → single head `b4e8f2a6c9d1`).

- [ ] **Step 2: Manual smoke via the app**

Use the `run-app` skill to start frontend + backend, then verify in the browser preview:
1. `/` lands on `/dashboard` with tiles + feed (30 days, all clients).
2. Each dropdown changes the URL and every band updates.
3. "Attention only" collapses the feed; an attention tile count links into a pre-filtered feed with a clearable chip.
4. A feed row navigates to the mapped client page.
5. Sidebar shows Dashboard first, active state on `/dashboard`, logo returns there.

- [ ] **Step 3: Hand off for merge**

Do NOT merge automatically. Report results and follow `superpowers:finishing-a-development-branch` for the merge decision. Prod migration (`b4e8f2a6c9d1`) ships via the `seenby-release` runbook at deploy time — flag it in the handoff summary.
