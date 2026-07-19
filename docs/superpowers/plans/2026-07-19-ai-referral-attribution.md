# AI Referral Attribution — GA4 Auto-Ingest (Spec 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the monthly AI-referral visitor number by pulling GA4 sessions from AI referrer domains into the existing `AiTrafficSnapshot` rows, with a per-platform breakdown — leaving every downstream consumer (revenue math, PDF, digest, client view) untouched.

**Architecture:** One service (`ga4_traffic_service`) wraps the GA4 Data API behind a single SeenBy service account; an admin-triggered sync upserts `AiTrafficSnapshot(source="ga4", breakdown=...)` per month; manual entry remains fully supported and is never silently overwritten.

**Tech Stack:** `google-analytics-data` (BetaAnalyticsDataClient), SQLAlchemy + Alembic, FastAPI, pytest (GA4 client fully mocked in tests), Next.js settings UI.

**Spec:** `docs/superpowers/specs/2026-07-19-ai-referral-attribution-design.md`

## Global Constraints

- Phase A only (visitors). Phase B (`ai_leads`) is explicitly out of scope for this plan.
- Sink is the existing `AiTrafficSnapshot` (UniqueConstraint client_id+period). Conflict rule: `manual` row for a period → skip + report; `ga4` row → update in place.
- Auth: env `GA4_SERVICE_ACCOUNT_JSON` (JSON string) — never per-client credentials, never in the repo. `.env.production.example` gains the documented entry.
- Client-facing framing keeps "~ / at least" hedging (referral attribution undercounts).
- Traffic stays informational — must NOT feed the GEO score (existing model docstring rule).
- Sync errors surface to the admin and never propagate into scan/report flows.
- Migration: `down_revision` = single current `alembic heads`. Branch: `feat/ga4-attribution` off master.

---

### Task 1: Migration + constants

**Files:**
- Modify: `backend/app/models/client.py` (add `ga4_property_id`)
- Modify: `backend/app/models/ai_traffic_snapshot.py` (add `source`, `breakdown`)
- Modify: `backend/app/core/constants.py` (add `AI_REFERRER_DOMAINS`)
- Create: `backend/alembic/versions/<newid>_add_ga4_traffic_fields.py`
- Test: `backend/tests/test_ai_traffic_model.py` (extend or create)

**Interfaces:**
- Produces: `Client.ga4_property_id: str | None`; `AiTrafficSnapshot.source: str` (server_default "manual"); `AiTrafficSnapshot.breakdown: dict | None` (JSON); `AI_REFERRER_DOMAINS: Final[dict[str, str]]` mapping domain → platform label.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_ai_traffic_model.py  (add)
from datetime import date
from app.models.client import Client
from app.models.ai_traffic_snapshot import AiTrafficSnapshot


def test_snapshot_source_defaults_manual_and_breakdown_roundtrips(db):
    c = Client(name="A", website="https://a.my", industry="x")
    db.add(c); db.commit()
    snap = AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1), ai_visitors=200,
                             breakdown={"chatgpt.com": 140, "perplexity.ai": 60})
    db.add(snap); db.commit()
    row = db.query(AiTrafficSnapshot).one()
    assert row.source == "manual"
    assert row.breakdown["chatgpt.com"] == 140
```

- [ ] **Step 2: Run — FAIL (`source`/`breakdown` unknown).**

- [ ] **Step 3: Implement**

`ai_traffic_snapshot.py` — add after `ai_visitors`:

```python
    # "manual" (admin-typed) | "ga4" (synced). A ga4 sync never overwrites a
    # manual row and vice versa without explicit admin action.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual", server_default="manual")
    # Per-referrer session counts, e.g. {"chatgpt.com": 140}. NULL for manual rows.
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

(add `String, JSON` to the sqlalchemy import). `client.py` — after `share_token_created_at`:

```python
    # GA4 property for automated AI-referral traffic sync. NULL = manual mode.
    ga4_property_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

`constants.py`:

```python
# Referrer domains classified as AI-sourced traffic (GA4 sync). Keys are
# matched against sessionSource/pageReferrer hosts (subdomain-tolerant).
# Extending this dict is the only change needed to track a new AI referrer.
AI_REFERRER_DOMAINS: Final = {
    "chatgpt.com":          "ChatGPT",
    "chat.openai.com":      "ChatGPT",
    "perplexity.ai":        "Perplexity",
    "gemini.google.com":    "Gemini",
    "bard.google.com":      "Gemini",
    "copilot.microsoft.com": "Copilot",
    "claude.ai":            "Claude",
    "you.com":              "You.com",
}
```

Migration: `add_column` × 3 (`clients.ga4_property_id` String(32) nullable; `ai_traffic_snapshots.source` String(16) server_default "manual" non-null; `ai_traffic_snapshots.breakdown` postgresql.JSONB nullable). No new table → no RLS statement needed.

- [ ] **Step 4: Run test — PASS. `alembic heads` single head. Commit** — `feat(ga4): traffic snapshot source/breakdown + client property id`

---

### Task 2: Referrer classification + month aggregation (pure logic)

**Files:**
- Create: `backend/app/services/ga4_traffic_service.py` (pure parts first)
- Test: `backend/tests/test_ga4_classification.py`

**Interfaces:**
- Produces: `classify_referrer(source: str) -> str | None` (platform label or None); `aggregate_rows(rows: list[tuple[str, str, int]]) -> dict[date, dict]` — input tuples `(yyyymm, source, sessions)`, output `{period_first_day: {"ai_visitors": int, "breakdown": {domain: sessions}}}`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_ga4_classification.py
from datetime import date
from app.services.ga4_traffic_service import aggregate_rows, classify_referrer


def test_classify_exact_and_subdomain_and_unknown():
    assert classify_referrer("chatgpt.com") == "ChatGPT"
    assert classify_referrer("www.perplexity.ai") == "Perplexity"
    assert classify_referrer("m.chat.openai.com") == "ChatGPT"
    assert classify_referrer("google.com") is None
    assert classify_referrer("notchatgpt.com") is None  # suffix must be dot-bounded


def test_aggregate_rows_by_month():
    rows = [
        ("202607", "chatgpt.com", 100),
        ("202607", "www.chatgpt.com", 40),
        ("202607", "perplexity.ai", 60),
        ("202606", "claude.ai", 10),
        ("202607", "google.com", 999),  # non-AI: dropped
    ]
    out = aggregate_rows(rows)
    assert out[date(2026, 7, 1)]["ai_visitors"] == 200
    assert out[date(2026, 7, 1)]["breakdown"]["chatgpt.com"] == 140
    assert out[date(2026, 6, 1)]["ai_visitors"] == 10
```

- [ ] **Step 2: Run — FAIL. Implement:**

```python
# backend/app/services/ga4_traffic_service.py
"""GA4 AI-referral traffic sync. Pure classification/aggregation here is
unit-tested without Google; the API call itself is isolated in _fetch_rows so
tests mock exactly one seam."""
import json
import os
import uuid
from datetime import date, datetime

import structlog
from sqlalchemy.orm import Session

from app.core.constants import AI_REFERRER_DOMAINS
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client

logger = structlog.get_logger()


def classify_referrer(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain, label in AI_REFERRER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return None


def _canonical_domain(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain in AI_REFERRER_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def aggregate_rows(rows: list[tuple[str, str, int]]) -> dict[date, dict]:
    out: dict[date, dict] = {}
    for yyyymm, source, sessions in rows:
        domain = _canonical_domain(source)
        if domain is None:
            continue
        period = date(int(yyyymm[:4]), int(yyyymm[4:6]), 1)
        bucket = out.setdefault(period, {"ai_visitors": 0, "breakdown": {}})
        bucket["ai_visitors"] += sessions
        bucket["breakdown"][domain] = bucket["breakdown"].get(domain, 0) + sessions
    return out
```

- [ ] **Step 3: Run — PASS. Commit** — `feat(ga4): referrer classification + monthly aggregation`

---

### Task 3: Sync — GA4 fetch seam + snapshot upsert with conflict rule

**Files:**
- Modify: `backend/app/services/ga4_traffic_service.py`
- Modify: `backend/pyproject.toml` (add `google-analytics-data` dependency; run `poetry lock`/install per repo convention)
- Modify: `backend/.env.production.example` (document `GA4_SERVICE_ACCOUNT_JSON`)
- Test: `backend/tests/test_ga4_sync.py`

**Interfaces:**
- Produces:
  - `_fetch_rows(property_id: str, months_back: int) -> list[tuple[str, str, int]]` — the ONLY function touching Google; raises `Ga4SyncError` on any API/auth problem.
  - `sync_client_traffic(client_id, db, months_back=2) -> SyncReport` — dataclass `(synced_periods: list[date], skipped_manual: list[date], error: str | None)`.
  - `class Ga4SyncError(Exception)`.

- [ ] **Step 1: Failing tests** (mock `_fetch_rows`)

```python
# backend/tests/test_ga4_sync.py
from datetime import date
from unittest.mock import patch
from app.models.client import Client
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.services.ga4_traffic_service import Ga4SyncError, sync_client_traffic


def _client(db, prop="123456789"):
    c = Client(name="A", website="https://a.my", industry="x", ga4_property_id=prop)
    db.add(c); db.commit()
    return c

ROWS = [("202607", "chatgpt.com", 140), ("202607", "perplexity.ai", 60)]


def test_sync_creates_ga4_snapshot(db):
    c = _client(db)
    with patch("app.services.ga4_traffic_service._fetch_rows", return_value=ROWS):
        report = sync_client_traffic(c.id, db)
    snap = db.query(AiTrafficSnapshot).one()
    assert (snap.ai_visitors, snap.source) == (200, "ga4")
    assert snap.breakdown == {"chatgpt.com": 140, "perplexity.ai": 60}
    assert report.synced_periods == [date(2026, 7, 1)]


def test_sync_updates_existing_ga4_row_but_skips_manual(db):
    c = _client(db)
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 7, 1),
                             ai_visitors=5, source="manual"))
    db.add(AiTrafficSnapshot(client_id=c.id, period=date(2026, 6, 1),
                             ai_visitors=5, source="ga4"))
    db.commit()
    rows = ROWS + [("202606", "claude.ai", 33)]
    with patch("app.services.ga4_traffic_service._fetch_rows", return_value=rows):
        report = sync_client_traffic(c.id, db)
    july = db.query(AiTrafficSnapshot).filter_by(period=date(2026, 7, 1)).one()
    june = db.query(AiTrafficSnapshot).filter_by(period=date(2026, 6, 1)).one()
    assert (july.ai_visitors, july.source) == (5, "manual")   # untouched
    assert (june.ai_visitors, june.source) == (33, "ga4")     # updated
    assert report.skipped_manual == [date(2026, 7, 1)]


def test_sync_without_property_id_reports_error(db):
    c = _client(db, prop=None)
    report = sync_client_traffic(c.id, db)
    assert report.error is not None


def test_fetch_failure_reports_error_and_writes_nothing(db):
    c = _client(db)
    with patch("app.services.ga4_traffic_service._fetch_rows", side_effect=Ga4SyncError("quota")):
        report = sync_client_traffic(c.id, db)
    assert report.error == "quota"
    assert db.query(AiTrafficSnapshot).count() == 0
```

- [ ] **Step 2: Run — FAIL. Implement (append to service):**

```python
from dataclasses import dataclass, field


class Ga4SyncError(Exception):
    pass


@dataclass
class SyncReport:
    synced_periods: list[date] = field(default_factory=list)
    skipped_manual: list[date] = field(default_factory=list)
    error: str | None = None


def _fetch_rows(property_id: str, months_back: int) -> list[tuple[str, str, int]]:
    """The single Google seam. Report: dimensions yearMonth + sessionSource,
    metric sessions, date range = first day of (current month - months_back)
    to today. Raises Ga4SyncError on any API/auth failure."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )
        from google.oauth2 import service_account

        creds_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")
        if not creds_json:
            raise Ga4SyncError("GA4_SERVICE_ACCOUNT_JSON is not configured")
        creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
        client = BetaAnalyticsDataClient(credentials=creds)

        today = date.today()
        start_month = today.month - months_back
        start_year = today.year
        while start_month < 1:
            start_month += 12
            start_year -= 1
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name="yearMonth"), Dimension(name="sessionSource")],
            metrics=[Metric(name="sessions")],
            date_ranges=[DateRange(start_date=f"{start_year}-{start_month:02d}-01",
                                   end_date=today.isoformat())],
        )
        response = client.run_report(request)
        return [
            (row.dimension_values[0].value, row.dimension_values[1].value,
             int(row.metric_values[0].value))
            for row in response.rows
        ]
    except Ga4SyncError:
        raise
    except Exception as exc:  # auth, quota, network — one seam, one error type
        raise Ga4SyncError(str(exc)) from exc


def sync_client_traffic(client_id: uuid.UUID, db: Session, months_back: int = 2) -> SyncReport:
    client = db.get(Client, client_id)
    if client is None or not client.ga4_property_id:
        return SyncReport(error="GA4 property not configured for this client")
    try:
        rows = _fetch_rows(client.ga4_property_id, months_back)
    except Ga4SyncError as exc:
        logger.error("ga4_sync_failed", client_id=str(client_id), error=str(exc))
        return SyncReport(error=str(exc))

    report = SyncReport()
    for period, data in sorted(aggregate_rows(rows).items()):
        existing = (
            db.query(AiTrafficSnapshot)
            .filter(AiTrafficSnapshot.client_id == client_id,
                    AiTrafficSnapshot.period == period)
            .first()
        )
        if existing is not None and existing.source == "manual":
            report.skipped_manual.append(period)
            continue
        if existing is None:
            existing = AiTrafficSnapshot(client_id=client_id, period=period)
            db.add(existing)
        existing.ai_visitors = data["ai_visitors"]
        existing.breakdown = data["breakdown"]
        existing.source = "ga4"
        report.synced_periods.append(period)
    db.commit()
    logger.info("ga4_sync_done", client_id=str(client_id),
                synced=len(report.synced_periods), skipped=len(report.skipped_manual))
    return report
```

Add `google-analytics-data` to pyproject dependencies. Grounding: the GA4 API shapes above are from training data — verify against current docs via `npx ctx7@latest library "Google Analytics Data API" "run report python BetaAnalyticsDataClient"` before finalizing `_fetch_rows`, and adjust imports/fields to what the docs show.

- [ ] **Step 3: Run — PASS (Google never called in tests). Commit** — `feat(ga4): sync service with manual-row protection`

---

### Task 4: Admin endpoint + settings UI

**Files:**
- Modify: `backend/app/api/v1/clients.py` (add `POST /clients/{id}/traffic/sync` returning the SyncReport; extend the client update schema/route with `ga4_property_id`)
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`
- Modify: `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` — "AI traffic (GA4)" card: property-ID input, "Sync traffic" button, last result line (synced months / skipped-manual months / error). Include the onboarding hint: "Grant Viewer access on the GA4 property to the SeenBy service account first."
- Test: `backend/tests/test_api_ga4_sync.py`

- [ ] **Step 1: API test** — sync endpoint returns report JSON (mock `_fetch_rows`); property id persists via settings update; error surfaces as 200-with-error-field (admin UX, not a 5xx).
- [ ] **Step 2: Implement; run tests.**
- [ ] **Step 3: Frontend card; `rtk lint && rtk tsc --noEmit`; browser-verify sync flow against a mocked/failing backend (error line renders).**
- [ ] **Step 4: Commit** — `feat(ga4): admin sync endpoint + settings card`

---

### Task 5: Breakdown display on existing traffic surfaces

**Files:**
- Grounding+modify: locate where `ai_visitors` renders — `backend/app/services/report_service.py` (grep `ai_visitors`), `backend/app/services/digest_service.py` money block (lines 298–313), `backend/app/api/v1/client_view.py` overview traffic block, and the client-view overview page
- Test: extend the touched surfaces' existing tests

**Interfaces:**
- Consumes: `AiTrafficSnapshot.breakdown`.
- Produces: a one-line per-platform breakdown ("ChatGPT 140 · Perplexity 61") rendered wherever the monthly AI-visitor number already appears, only when `breakdown` is non-null. Labels via `AI_REFERRER_DOMAINS` values.

- [ ] **Step 1: Tests:** digest/report/client-view payloads include the formatted breakdown when present, omit when null; "~/at least" hedge present in client copy (e.g. "at least {n} visitors came from AI tools").
- [ ] **Step 2: Implement a shared helper in `ga4_traffic_service`:**

```python
def format_breakdown(breakdown: dict | None) -> str | None:
    if not breakdown:
        return None
    parts = sorted(breakdown.items(), key=lambda kv: -kv[1])
    return " · ".join(f"{AI_REFERRER_DOMAINS.get(d, d)} {n:,}" for d, n in parts)
```

Use it in each surface. `revenue_service` is untouched (verified: it takes `ai_visitors: int | None`).

- [ ] **Step 3: Full backend suite + frontend checks. Commit** — `feat(ga4): per-platform traffic breakdown on client surfaces`

---

### Task 6: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify skill.
- [ ] Live walkthrough (with a real GA4 property if available, else mocked): set property id in settings → sync → snapshot row appears with source "ga4" → digest/PDF/overview show number + breakdown → manual row for another month untouched.
- [ ] Confirm `.env.production.example` documents `GA4_SERVICE_ACCOUNT_JSON` and docs/deploy-vps.md env list mentions it. Finish branch.

## Self-review notes

- Spec Phase A fully covered (T1 model, T2–3 sync+conflict rule, T4 admin, T5 surfaces). Phase B intentionally absent per spec.
- Scheduled auto-sync deferred exactly as spec says (admin-triggered only; the Celery task is a one-liner follow-up once trusted).
- The only untested seam is `_fetch_rows` (thin, single-purpose, doc-verified via context7 step).
