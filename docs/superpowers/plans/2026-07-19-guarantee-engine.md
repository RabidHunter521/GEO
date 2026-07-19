# Guarantee Engine (Spec 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-client baseline → target → deadline commitment object, with derived pace states, admin-gated terminal outcomes, and display on admin panel, client view, PDF, and digest — plus at-risk alerting to Faris.

**Architecture:** One `Guarantee` model (single active per client) + `guarantee_service` (compute-on-read progress, admin-only resolution) + a best-effort post-scan state-transition check that emails/Telegrams Faris. Surfaces read `get_guarantee_progress`.

**Tech Stack:** SQLAlchemy + Alembic (RLS), FastAPI, pytest, Next.js, WeasyPrint (existing report pipeline).

**Spec:** `docs/superpowers/specs/2026-07-19-guarantee-engine-design.md`

## Global Constraints

- Metric ∈ {"overall", "ai_citability"}; default "ai_citability".
- Exactly one `active` guarantee per client (service-enforced).
- Derived states: `met` / `on_track` / `at_risk` / `deadline_passed`; terminal `met`/`missed`/`void` only via admin resolution.
- No automated client-facing "missed" messaging; `at_risk` renders neutrally on client surfaces (numbers, no red alarm).
- Alert fires on state TRANSITION only, best-effort (rollback + swallow), never blocks a scan.
- Client-facing copy through `language_sanitizer`; CLAUDE.md §2 vocabulary; colors via existing 3-band utilities only.
- Migration: `down_revision` = single current `alembic heads` at implementation time.
- Branch: `feat/guarantee-engine` off master. Tests: `cd backend && python -m pytest <file> -v`.

---

### Task 1: `Guarantee` model + migration

**Files:**
- Create: `backend/app/models/guarantee.py`
- Modify: `backend/tests/conftest.py` (add `guarantee` to model imports)
- Create: `backend/alembic/versions/<newid>_add_guarantees.py`
- Modify: `backend/app/core/constants.py`
- Test: `backend/tests/test_guarantee_model.py`

**Interfaces:**
- Produces: `Guarantee(id, client_id, metric, baseline_value, target_value, start_date, deadline_date, status, last_state, resolved_at, admin_note, created_at)`; constants `GUARANTEE_METRICS = ("ai_citability", "overall")`, `GUARANTEE_STATUSES = ("active", "met", "missed", "void")`, `GUARANTEE_GRACE_FRACTION = 0.15`.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_guarantee_model.py
from datetime import date
from app.models.client import Client
from app.models.guarantee import Guarantee


def test_guarantee_roundtrip(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c); db.commit()
    g = Guarantee(client_id=c.id, metric="ai_citability", baseline_value=38,
                  target_value=55, start_date=date(2026, 7, 1),
                  deadline_date=date(2026, 9, 29))
    db.add(g); db.commit()
    row = db.query(Guarantee).one()
    assert row.status == "active"
    assert row.last_state is None
```

- [ ] **Step 2: Run — FAIL (module missing).**

- [ ] **Step 3: Implement**

```python
# backend/app/models/guarantee.py
import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Text, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Guarantee(Base):
    """A written commitment: lift `metric` from baseline to target by deadline.

    status: "active" | "met" | "missed" | "void" — terminal states only via
    explicit admin resolution (system suggests, admin gates; a client never
    learns "missed" from an automated flow). last_state stores the most recent
    DERIVED pace state ("on_track"/"at_risk"/"met"/"deadline_passed") so the
    post-scan check can alert on transitions only.
    The commercial remedy (e.g. free month) lives in the engagement letter,
    not in code — admin_note carries the paper trail.
    """

    __tablename__ = "guarantees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False, default="ai_citability")
    baseline_value: Mapped[int] = mapped_column(Integer, nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    deadline_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    last_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

Constants (after the remediation block):

```python
GUARANTEE_METRICS: Final = ("ai_citability", "overall")
GUARANTEE_STATUSES: Final = ("active", "met", "missed", "void")
# Pace grace: no "at_risk" before this fraction of the period has elapsed,
# so week 1 of a 90-day guarantee is never instantly behind.
GUARANTEE_GRACE_FRACTION: Final = 0.15
```

Migration mirrors Task 1 of the control-query plan (create table, FK CASCADE, `ENABLE ROW LEVEL SECURITY`, server defaults for status). Register model in conftest imports.

- [ ] **Step 4: Run test — PASS. `alembic heads` — one head. Commit** — `feat(guarantee): model + migration`

---

### Task 2: `guarantee_service` — create / progress / resolve

**Files:**
- Create: `backend/app/services/guarantee_service.py`
- Test: `backend/tests/test_guarantee_service.py`

**Interfaces:**
- Consumes: `Guarantee` (Task 1); `GeoScore` model (fields used: `client_id, ai_citability, overall_score, computed_at`).
- Produces:
  - `create_guarantee(client_id, metric, target_value, deadline_date, db, baseline_override=None, start_date=None) -> Guarantee` — raises `ValueError("active guarantee exists")` on duplicate; baseline auto-filled from latest GeoScore's metric value (rounded int) unless overridden; raises `ValueError("no completed scan to baseline from")` when no score and no override.
  - `get_guarantee_progress(client_id, db) -> GuaranteeProgress | None` — dataclass `(guarantee: Guarantee, current_value: float | None, points_needed: int, points_gained: float, days_total: int, days_remaining: int, state: str)`.
  - `resolve_guarantee(guarantee_id, outcome, db, note=None) -> Guarantee` — outcome ∈ {"met","missed","void"}; sets `resolved_at`; raises on already-resolved.
  - `derive_state(g, current_value, today) -> str` — pure function (unit-testable).

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_guarantee_service.py
from datetime import date, timedelta
import pytest
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee
from app.services.guarantee_service import (
    create_guarantee, derive_state, get_guarantee_progress, resolve_guarantee,
)


def _client_with_score(db, citability=40.0, overall=50.0):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c); db.commit()
    db.add(GeoScore(client_id=c.id, ai_citability=citability, brand_authority=50.0,
                    content_quality=50.0, technical_foundations=0.0,
                    structured_data=0.0, overall_score=overall))
    db.commit()
    return c


def _g(baseline=40, target=60, start=None, deadline=None):
    start = start or date.today() - timedelta(days=30)
    deadline = deadline or date.today() + timedelta(days=60)
    return Guarantee(metric="ai_citability", baseline_value=baseline, target_value=target,
                     start_date=start, deadline_date=deadline, status="active")


def test_create_autofills_baseline_and_blocks_duplicate(db):
    c = _client_with_score(db, citability=42.4)
    g = create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db)
    assert g.baseline_value == 42
    with pytest.raises(ValueError):
        create_guarantee(c.id, "ai_citability", 65, date.today() + timedelta(days=90), db)


def test_derive_states():
    today = date.today()
    # met early
    assert derive_state(_g(), 61.0, today) == "met"
    # grace window: 5 days into 100 → never at_risk
    g = _g(start=today - timedelta(days=5), deadline=today + timedelta(days=95))
    assert derive_state(g, 40.0, today) == "on_track"
    # behind pace at 50% elapsed with 0 gained
    g = _g(start=today - timedelta(days=45), deadline=today + timedelta(days=45))
    assert derive_state(g, 40.0, today) == "at_risk"
    # ahead of pace
    assert derive_state(g, 52.0, today) == "on_track"
    # past deadline, unmet
    g = _g(start=today - timedelta(days=100), deadline=today - timedelta(days=1))
    assert derive_state(g, 50.0, today) == "deadline_passed"


def test_resolve_locks(db):
    c = _client_with_score(db)
    g = create_guarantee(c.id, "ai_citability", 60, date.today() + timedelta(days=90), db)
    resolve_guarantee(g.id, "void", db, note="client paused")
    assert g.status == "void" and g.resolved_at is not None
    with pytest.raises(ValueError):
        resolve_guarantee(g.id, "met", db)


def test_progress_none_without_guarantee(db):
    c = _client_with_score(db)
    assert get_guarantee_progress(c.id, db) is None
```

- [ ] **Step 2: Run — FAIL.**

- [ ] **Step 3: Implement**

```python
# backend/app/services/guarantee_service.py
"""Guarantee engine — commitment tracking. System derives pace; only the admin
flips terminal outcomes (assessment-service pattern: suggest, never auto-tell
a client "missed")."""
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import GUARANTEE_GRACE_FRACTION, GUARANTEE_METRICS
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee


@dataclass
class GuaranteeProgress:
    guarantee: Guarantee
    current_value: float | None
    points_needed: int
    points_gained: float
    days_total: int
    days_remaining: int
    state: str


def _latest_metric_value(client_id: uuid.UUID, metric: str, db: Session) -> float | None:
    gs = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
    if gs is None:
        return None
    return gs.ai_citability if metric == "ai_citability" else gs.overall_score


def _active(client_id: uuid.UUID, db: Session) -> Guarantee | None:
    return (
        db.query(Guarantee)
        .filter(Guarantee.client_id == client_id, Guarantee.status == "active")
        .first()
    )


def create_guarantee(
    client_id: uuid.UUID, metric: str, target_value: int, deadline_date: date,
    db: Session, baseline_override: int | None = None, start_date: date | None = None,
) -> Guarantee:
    if metric not in GUARANTEE_METRICS:
        raise ValueError(f"Invalid metric: {metric}")
    if _active(client_id, db) is not None:
        raise ValueError("active guarantee exists")
    baseline = baseline_override
    if baseline is None:
        current = _latest_metric_value(client_id, metric, db)
        if current is None:
            raise ValueError("no completed scan to baseline from")
        baseline = round(current)
    g = Guarantee(
        client_id=client_id, metric=metric, baseline_value=baseline,
        target_value=target_value, start_date=start_date or date.today(),
        deadline_date=deadline_date,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def derive_state(g: Guarantee, current_value: float | None, today: date) -> str:
    if current_value is not None and current_value >= g.target_value:
        return "met"
    if today > g.deadline_date:
        return "deadline_passed"
    days_total = max((g.deadline_date - g.start_date).days, 1)
    elapsed = max((today - g.start_date).days, 0)
    if elapsed / days_total <= GUARANTEE_GRACE_FRACTION:
        return "on_track"
    if current_value is None:
        return "on_track"  # no scan yet in period — nothing to judge
    needed = g.target_value - g.baseline_value
    gained = current_value - g.baseline_value
    expected = (elapsed / days_total) * needed
    return "on_track" if gained >= expected else "at_risk"


def get_guarantee_progress(client_id: uuid.UUID, db: Session) -> GuaranteeProgress | None:
    g = _active(client_id, db)
    if g is None:
        return None
    current = _latest_metric_value(client_id, g.metric, db)
    today = date.today()
    return GuaranteeProgress(
        guarantee=g,
        current_value=current,
        points_needed=g.target_value - g.baseline_value,
        points_gained=round((current - g.baseline_value), 2) if current is not None else 0.0,
        days_total=max((g.deadline_date - g.start_date).days, 1),
        days_remaining=max((g.deadline_date - today).days, 0),
        state=derive_state(g, current, today),
    )


def resolve_guarantee(
    guarantee_id: uuid.UUID, outcome: str, db: Session, note: str | None = None
) -> Guarantee:
    if outcome not in ("met", "missed", "void"):
        raise ValueError(f"Invalid outcome: {outcome}")
    g = db.get(Guarantee, guarantee_id)
    if g is None:
        raise ValueError("guarantee not found")
    if g.status != "active":
        raise ValueError("guarantee already resolved")
    g.status = outcome
    g.resolved_at = datetime.utcnow()
    if note:
        g.admin_note = note
    db.commit()
    db.refresh(g)
    return g
```

- [ ] **Step 4: Run — PASS. Commit** — `feat(guarantee): service — create/progress/derive/resolve`

---

### Task 3: Post-scan transition check + admin alert

**Files:**
- Create: `backend/app/services/guarantee_alert.py` (kept separate from `alert_service` to avoid touching its 412 lines; same email/Telegram helpers imported from it — grounding: find the send helpers `alert_service` uses, e.g. its email/Telegram functions, and reuse)
- Modify: `backend/app/services/scan_service.py` (`run_scan`, in the post-commit best-effort block after the action-center refresh, ~line 333)
- Test: `backend/tests/test_guarantee_alert.py`

**Interfaces:**
- Consumes: `get_guarantee_progress`, `Guarantee.last_state`.
- Produces: `check_guarantee_transition(client, db) -> None` — computes current state; if state != `guarantee.last_state` and state in ("at_risk", "deadline_passed"), sends admin alert (email ALERTS_EMAIL + Telegram best-effort); ALWAYS persists `last_state` after evaluation.

- [ ] **Step 1: Failing tests** — with a mocked send helper: (a) first evaluation to `at_risk` sends once and sets `last_state`; (b) second evaluation in same state sends nothing; (c) transition back to `on_track` sends nothing but updates `last_state`; (d) exception in send is swallowed (no raise) and scan flow unaffected.

```python
# backend/tests/test_guarantee_alert.py
from datetime import date, timedelta
from unittest.mock import patch
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.guarantee import Guarantee
from app.services.guarantee_alert import check_guarantee_transition


def _setup(db, citability):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c); db.commit()
    db.add(GeoScore(client_id=c.id, ai_citability=citability, brand_authority=0.0,
                    content_quality=0.0, technical_foundations=0.0,
                    structured_data=0.0, overall_score=citability))
    g = Guarantee(client_id=c.id, metric="ai_citability", baseline_value=40,
                  target_value=60, start_date=date.today() - timedelta(days=45),
                  deadline_date=date.today() + timedelta(days=45), status="active")
    db.add(g); db.commit()
    return c, g


def test_transition_to_at_risk_alerts_once(db):
    c, g = _setup(db, citability=40.0)  # 0 gained at 50% elapsed → at_risk
    with patch("app.services.guarantee_alert._send_admin_alert") as send:
        check_guarantee_transition(c, db)
        check_guarantee_transition(c, db)
    assert send.call_count == 1
    assert g.last_state == "at_risk"


def test_send_failure_is_swallowed(db):
    c, g = _setup(db, citability=40.0)
    with patch("app.services.guarantee_alert._send_admin_alert", side_effect=RuntimeError):
        check_guarantee_transition(c, db)  # must not raise
    assert g.last_state == "at_risk"
```

- [ ] **Step 2: Run — FAIL. Implement:**

```python
# backend/app/services/guarantee_alert.py
"""Post-scan guarantee pace check. Best-effort by contract: callers wrap in the
scan post-commit try/except; internally a send failure is also swallowed so
last_state still persists."""
import structlog
from sqlalchemy.orm import Session

from app.models.client import Client
from app.services.guarantee_service import get_guarantee_progress

logger = structlog.get_logger()

_ALERT_STATES = ("at_risk", "deadline_passed")


def _send_admin_alert(client: Client, state: str, progress) -> None:
    # Reuse alert_service's existing admin email + Telegram helpers.
    from app.services.alert_service import send_admin_email  # grounding: use the actual helper name found in alert_service.py
    g = progress.guarantee
    send_admin_email(
        subject=f"[SeenBy] Guarantee {state.replace('_', ' ')}: {client.name}",
        body=(
            f"Client: {client.name}\n"
            f"Commitment: {g.metric} {g.baseline_value} → {g.target_value} by {g.deadline_date}\n"
            f"Current: {progress.current_value}\n"
            f"State: {state} ({progress.days_remaining} days remaining)\n"
        ),
    )


def check_guarantee_transition(client: Client, db: Session) -> None:
    progress = get_guarantee_progress(client.id, db)
    if progress is None:
        return
    g = progress.guarantee
    state = progress.state
    if state != g.last_state and state in _ALERT_STATES:
        try:
            _send_admin_alert(client, state, progress)
        except Exception as exc:
            logger.error("guarantee_alert_send_failed", client_id=str(client.id), error=str(exc))
    g.last_state = state
    db.commit()
```

Grounding note: before writing `_send_admin_alert`, open `backend/app/services/alert_service.py` and use its actual admin-email/Telegram helper names + signatures (it sends to ALERTS_EMAIL and pushes Telegram best-effort). Wire into `scan_service.run_scan` post-commit block, after the action-center refresh:

```python
        try:
            from app.services.guarantee_alert import check_guarantee_transition
            check_guarantee_transition(client, db)
        except Exception as exc:
            db.rollback()
            logger.error("guarantee_check_failed", scan_id=str(scan_id), error=str(exc))
```

- [ ] **Step 3: Run tests + full scan-suite. Commit** — `feat(guarantee): post-scan pace check with transition-only admin alert`

---

### Task 4: Admin API + settings/detail UI

**Files:**
- Create: `backend/app/schemas/guarantee.py`; routes in `backend/app/api/v1/clients.py` (mirror existing per-client resources): `GET /clients/{id}/guarantee` (progress or null), `POST /clients/{id}/guarantee`, `POST /clients/{id}/guarantee/{gid}/resolve`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`
- Modify: `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` (create/void card) and the client detail page `frontend/src/app/clients/[id]/page.tsx` (progress widget with resolve action when `deadline_passed`)
- Test: `backend/tests/test_api_guarantee.py`

- [ ] **Step 1: API tests** — create (409/422 on duplicate active), progress payload shape, resolve, 404 wrong client. Mirror `test_api_provenance.py` fixture style.
- [ ] **Step 2: Implement thin routes over the service; run tests.**
- [ ] **Step 3: Frontend widget:** baseline → current → target with a progress bar (existing `FrequencyBar`-style pattern), deadline, derived state chip (state→color: met/on_track green, at_risk yellow, deadline_passed red via existing score-color utilities). Resolve dialog with outcome + note. `rtk lint && rtk tsc --noEmit`.
- [ ] **Step 4: Commit** — `feat(guarantee): admin API + settings/detail UI`

---

### Task 5: Client surfaces — view card, PDF block, digest line

**Files:**
- Modify: `backend/app/api/v1/client_view.py` (overview response: optional `commitment` block — whitelisted fields only: metric label, baseline, target, current, deadline ISO, state collapsed for clients)
- Modify: `frontend/src/app/view/[token]/page.tsx` ("Our commitment" card)
- Modify: `backend/app/services/report_service.py` (commitment block near the header/score section — mirror an existing section builder)
- Modify: `backend/app/services/digest_service.py` (one line when active: current vs target + days left; extend `DigestData` with `commitment_line: str | None`)
- Test: `backend/tests/test_client_view_guarantee.py` + digest/report test extensions

**Interfaces:**
- Consumes: `get_guarantee_progress`.
- Produces: client-state collapse rule — clients see state as: `met` → "achieved", `on_track`/`at_risk` → "in progress" (neutral; numbers speak), `deadline_passed` → hidden until admin resolves; `void` → hidden; `missed` → shown only when status=="missed" AND admin resolved, framed via admin_note-free copy.

- [ ] **Step 1: Backend tests:** overview has no `commitment` when none/void; `at_risk` serializes as `"in_progress"` (no alarm state leaks); `deadline_passed` absent; `missed` present only post-resolution. Assert no `last_state`/`admin_note` in payload.
- [ ] **Step 2: Implement backend block; exact client copy:** `"We committed to lifting your AI visibility from {baseline} to {target} by {deadline}. Today: {current}."` — run through `language_sanitizer` in tests.
- [ ] **Step 3: View card + PDF block + digest line; frontend lint/type-check; backend suite.**
- [ ] **Step 4: Commit** — `feat(guarantee): commitment on client view, PDF, and digest`

---

### Task 6: Final verification gate

- [ ] Full backend suite + `alembic heads` single head.
- [ ] seenby-verify skill; live walkthrough: create guarantee on a seeded client → scan → widget states; resolve → client-view behavior per state table.
- [ ] Language sweep of diff for banned vocabulary. Finish branch per superpowers:finishing-a-development-branch.

## Self-review notes

- Spec state table → Task 2 `derive_state` (+ grace constant); surfaces table → Tasks 4–5; alerting → Task 3 (transition-only via persisted `last_state`, which the spec's model gained for exactly this).
- Deviation: spec listed `last_state` implicitly ("evaluated at scan completion… fires on transition only") — made explicit as a column; recorded in the spec's model in Task 1.
- Credibility dependency (launch after Spec 1) is sequencing guidance, not a code dependency — no task blocks on it.
