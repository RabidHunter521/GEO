# SeenBy AI Visibility Index (Spec 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggregate every scan (clients, prospects, competitor rows) into anonymized monthly visibility-frequency buckets by industry × region × platform, stored from day one, published only above N≥3 — with an admin bucket view, a gated client benchmark line, and an export for the public quarterly report.

**Architecture:** `IndexSnapshot` model + idempotent `index_service.compute_period` wired as a monthly Celery maintenance task with an admin recompute trigger and a one-time backfill. Extends (does not replace) the existing `benchmark_service` peer percentile — reuses `MIN_BENCHMARK_PEERS` and `compute_percentile`.

**Tech Stack:** SQLAlchemy + Alembic (RLS), Celery beat (maintenance_tasks pattern), FastAPI, pytest, Next.js.

**Spec:** `docs/superpowers/specs/2026-07-19-visibility-index-design.md` (note its "Current State" section on `benchmark_service`).

## Global Constraints

- Snapshots computed regardless of N; anything client-/export-facing requires `business_count >= MIN_BENCHMARK_PEERS` (reuse the existing constant, value 3).
- Aggregates only — no business names or client IDs in any non-admin payload.
- Derivation excludes: control rows (`is_control`, if Spec 1 shipped), pitch scans (`is_pitch`, if Spec 6 shipped), internal clients (`is_internal`, if Spec 5 shipped). Each exclusion is written defensively with `getattr`/hasattr so this plan works whether or not those columns exist yet.
- Each business counts once per bucket (unweighted mean across businesses).
- Industry normalization via `INDUSTRY_ALIASES` constants map; data fix = constants edit + recompute.
- No public web endpoint — export is admin-only CSV/JSON.
- Migration: `down_revision` = single current `alembic heads`. Branch: `feat/visibility-index` off master.

---

### Task 1: `IndexSnapshot` model + migration + alias map

**Files:**
- Create: `backend/app/models/index_snapshot.py`
- Modify: `backend/tests/conftest.py` (register model)
- Modify: `backend/app/core/constants.py` (add `INDUSTRY_ALIASES`)
- Create: `backend/alembic/versions/<newid>_add_index_snapshots.py`
- Test: `backend/tests/test_index_snapshot_model.py`

**Interfaces:**
- Produces: `IndexSnapshot(id, industry, region, platform, period, business_count, query_count, visibility_frequency, avg_recommendation_position, computed_at)` with `UniqueConstraint(industry, region, platform, period)`; `normalize_industry(raw: str) -> str` helper in constants-adjacent service (Task 2); `INDUSTRY_ALIASES: Final[dict[str, str]]` seed:

```python
INDUSTRY_ALIASES: Final = {
    "dentist": "dental clinic",
    "dental": "dental clinic",
    "dental practice": "dental clinic",
    "physiotherapist": "physiotherapy clinic",
    "physio": "physiotherapy clinic",
    "aesthetic clinic": "aesthetics clinic",
}
```

- [ ] **Step 1: Failing test** — roundtrip + unique constraint violation on duplicate bucket (use `pytest.raises(IntegrityError)` after second insert + flush).
- [ ] **Step 2: Run — FAIL. Implement model:**

```python
# backend/app/models/index_snapshot.py
import uuid
from datetime import date, datetime
from sqlalchemy import String, Integer, Numeric, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class IndexSnapshot(Base):
    """Anonymized monthly market bucket: how often AI sees businesses of an
    industry in a region, per platform. The compounding data asset behind the
    SeenBy AI Visibility Index. Aggregates only — never names a business.
    Buckets below MIN_BENCHMARK_PEERS businesses are stored but never leave
    the admin panel."""

    __tablename__ = "index_snapshots"
    __table_args__ = (
        UniqueConstraint("industry", "region", "platform", "period",
                         name="uq_index_snapshot_bucket"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)  # first of month
    business_count: Mapped[int] = mapped_column(Integer, nullable=False)
    query_count: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility_frequency: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    avg_recommendation_position: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

Migration mirrors prior table patterns + `ENABLE ROW LEVEL SECURITY`.

- [ ] **Step 3: Run — PASS. Commit** — `feat(index): IndexSnapshot model + industry alias map`

---

### Task 2: Derivation — `index_service.compute_period`

**Files:**
- Create: `backend/app/services/index_service.py`
- Test: `backend/tests/test_index_service.py`

**Interfaces:**
- Produces:
  - `normalize_industry(raw: str) -> str` — lowercased/trimmed, alias-mapped.
  - `client_region(client) -> str` — `client.state or client.country or "Malaysia"`.
  - `compute_period(period: date, db) -> int` — recomputes ALL buckets for that month idempotently (delete-then-insert for the period), returns bucket count.
  - Per-business observation rule: for **clients/prospects**, its rows are `competitor_id IS NULL` result rows of its scans completed in the month; for **competitors**, its rows are the `competitor_id == <that competitor>` rows (attributed to the competitor as a business, bucketed under the OWNING client's industry/region). Frequency per business = detected/total over the month; bucket value = unweighted mean.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_index_service.py
from datetime import date, datetime
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.index_snapshot import IndexSnapshot
from app.services.index_service import compute_period, normalize_industry


def test_normalize_industry_aliases_and_passthrough():
    assert normalize_industry(" Dentist ") == "dental clinic"
    assert normalize_industry("Pet Grooming") == "pet grooming"


def _scan_with_rows(db, client, seen, total, platform="chatgpt", competitor=None, when=None):
    s = Scan(client_id=client.id, status="completed")
    s.completed_at = when or datetime(2026, 7, 10)
    db.add(s); db.commit()
    rows = [ScanQueryResult(scan_id=s.id, platform=platform, category="recommendation",
                            query_text=f"q{i}", brand_detected=i < seen,
                            competitor_id=competitor.id if competitor else None)
            for i in range(total)]
    db.add_all(rows); db.commit()


def test_bucket_unweighted_mean_and_competitor_inclusion(db):
    a = Client(name="A", website="https://a.my", industry="Dentist", state="KL")
    b = Client(name="B", website="https://b.my", industry="dental clinic", state="KL")
    db.add_all([a, b]); db.commit()
    rival = Competitor(client_id=a.id, name="R", website="https://r.my")
    db.add(rival); db.commit()
    _scan_with_rows(db, a, seen=2, total=4)               # A: 50%
    _scan_with_rows(db, b, seen=4, total=4)               # B: 100%
    _scan_with_rows(db, a, seen=0, total=2, competitor=rival)  # rival: 0%
    compute_period(date(2026, 7, 1), db)
    snap = db.query(IndexSnapshot).filter_by(
        industry="dental clinic", region="KL", platform="chatgpt").one()
    assert snap.business_count == 3
    assert float(snap.visibility_frequency) == 50.0  # mean(50,100,0)
    assert snap.query_count == 10


def test_idempotent_recompute(db):
    a = Client(name="A", website="https://a.my", industry="dentist", state="KL")
    db.add(a); db.commit()
    _scan_with_rows(db, a, seen=1, total=2)
    compute_period(date(2026, 7, 1), db)
    compute_period(date(2026, 7, 1), db)
    assert db.query(IndexSnapshot).count() == 1


def test_excludes_other_months_and_incomplete_scans(db):
    a = Client(name="A", website="https://a.my", industry="dentist", state="KL")
    db.add(a); db.commit()
    _scan_with_rows(db, a, seen=1, total=2, when=datetime(2026, 6, 15))
    compute_period(date(2026, 7, 1), db)
    assert db.query(IndexSnapshot).count() == 0
```

- [ ] **Step 2: Run — FAIL. Implement** (delete-for-period then insert; defensive exclusions):

```python
# backend/app/services/index_service.py  (core sketch — full code in step)
"""SeenBy AI Visibility Index — anonymized market aggregation.

Every completed scan is a market observation: the client's own rows, a
prospect's rows, and each competitor's rows all measure "how often is a
business of this industry in this region seen by AI". Buckets are stored at
any N; MIN_BENCHMARK_PEERS gates everything that leaves the admin panel."""
import calendar
import uuid
from collections import defaultdict
from datetime import date, datetime

import structlog
from sqlalchemy.orm import Session

from app.core.constants import INDUSTRY_ALIASES
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.index_snapshot import IndexSnapshot
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult

logger = structlog.get_logger()


def normalize_industry(raw: str) -> str:
    key = (raw or "").strip().lower()
    return INDUSTRY_ALIASES.get(key, key)


def client_region(client: Client) -> str:
    return client.state or client.country or "Malaysia"


def _month_bounds(period: date) -> tuple[datetime, datetime]:
    last = calendar.monthrange(period.year, period.month)[1]
    return (datetime(period.year, period.month, 1),
            datetime(period.year, period.month, last, 23, 59, 59))


def compute_period(period: date, db: Session) -> int:
    start, end = _month_bounds(period)
    db.query(IndexSnapshot).filter(IndexSnapshot.period == period).delete()

    clients = db.query(Client).filter(Client.archived_at.is_(None)).all()
    clients = [c for c in clients if not getattr(c, "is_internal", False)]
    competitors_by_client: dict[uuid.UUID, list[Competitor]] = defaultdict(list)
    for comp in db.query(Competitor).all():
        competitors_by_client[comp.client_id].append(comp)

    # (industry, region, platform) -> {business_key: [seen, total]}
    buckets: dict[tuple[str, str, str], dict[str, list[int]]] = defaultdict(dict)
    positions: dict[tuple[str, str, str], list[int]] = defaultdict(list)

    for client in clients:
        industry, region = normalize_industry(client.industry), client_region(client)
        scans = (
            db.query(Scan)
            .filter(Scan.client_id == client.id, Scan.status == "completed",
                    Scan.completed_at >= start, Scan.completed_at <= end)
            .all()
        )
        scans = [s for s in scans if not getattr(s, "is_pitch", False)]
        if not scans:
            continue
        rows = (
            db.query(ScanQueryResult)
            .filter(ScanQueryResult.scan_id.in_([s.id for s in scans]))
            .all()
        )
        rows = [r for r in rows if not getattr(r, "is_control", False)]
        comp_names = {c.id: c.name for c in competitors_by_client[client.id]}
        for r in rows:
            key = (industry, region, r.platform)
            business = f"client:{client.id}" if r.competitor_id is None \
                else f"competitor:{r.competitor_id}"
            stat = buckets[key].setdefault(business, [0, 0])
            stat[1] += 1
            if r.brand_detected:
                stat[0] += 1
            if r.competitor_id is None and r.recommendation_position:
                positions[key].append(r.recommendation_position)

    count = 0
    for (industry, region, platform), businesses in buckets.items():
        freqs = [seen / total * 100 for seen, total in businesses.values() if total]
        if not freqs:
            continue
        pos = positions.get((industry, region, platform))
        db.add(IndexSnapshot(
            industry=industry, region=region, platform=platform, period=period,
            business_count=len(freqs),
            query_count=sum(t for _, t in businesses.values()),
            visibility_frequency=round(sum(freqs) / len(freqs), 2),
            avg_recommendation_position=round(sum(pos) / len(pos), 2) if pos else None,
        ))
        count += 1
    db.commit()
    logger.info("index_period_computed", period=str(period), buckets=count)
    return count
```

- [ ] **Step 3: Run — PASS. Commit** — `feat(index): monthly bucket derivation, idempotent`

---

### Task 3: Celery task + backfill + admin recompute endpoint

**Files:**
- Modify: `backend/workers/tasks/maintenance_tasks.py` (add `run_index_aggregation` — computes previous month + current month; mirror the existing task structure/logging exactly)
- Grounding+modify: the beat schedule (find where `run_data_retention` is scheduled — `backend/workers/celery_app.py` or settings — and add a monthly entry)
- Create: `backend/app/api/v1/index.py` (admin: `POST /index/recompute?months_back=N` looping `compute_period`; `GET /index/buckets?period=` listing snapshots) + register in `router.py`
- Test: `backend/tests/test_api_index.py`

- [ ] **Step 1: API tests** — recompute over seeded 2-month history creates snapshots for both months; bucket listing returns all buckets (admin sees sub-threshold ones too, flagged `publishable: bool`).
- [ ] **Step 2: Implement task + routes (thin; logic stays in index_service). Backfill = calling recompute with `months_back` covering history — no separate script.**
- [ ] **Step 3: Run suite. Commit** — `feat(index): monthly aggregation task + admin recompute/list`

---

### Task 4: Admin bucket view + export

**Files:**
- Create: `frontend/src/app/clients/index-admin/page.tsx` — NOTE: CLAUDE.md §9 locks the nav; adding a page requires updating §9 in the same commit. Alternative (preferred, zero nav change): render the bucket table as a new section on the existing `/clients/gap-matrix` page. Decide with Faris at review; default = gap-matrix section.
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`
- Export: `GET /index/export?period=&format=csv` in `api/v1/index.py` — publishable buckets only (`business_count >= MIN_BENCHMARK_PEERS`), CSV columns `industry,region,platform,period,business_count,visibility_frequency,avg_recommendation_position`
- Test: extend `backend/tests/test_api_index.py` — export excludes sub-threshold buckets; no business identifiers in output.

- [ ] Steps: failing export test → implement → bucket table UI (industry × region rows, platform columns, N badge, trend vs previous month) → lint/type-check → commit — `feat(index): admin bucket view + publishable-only export`

---

### Task 5: Client-facing benchmark line (gated)

**Files:**
- Modify: `backend/app/api/v1/client_view.py` overview — optional `market_benchmark` block: `{industry_label, region, market_visibility_frequency, your_visibility_frequency}` from the latest computed period's bucket matching the client (client's own frequency from its GeoScore/platform data as already exposed), present only when the bucket's `business_count >= MIN_BENCHMARK_PEERS`
- Modify: `frontend/src/app/view/[token]/page.tsx` — card: "Businesses like yours in {region} are seen by AI {X}% of the time. You: {Y}%."
- Modify: `backend/app/services/report_service.py` — same line in the score section (grounding: mirror an existing optional section builder)
- Test: `backend/tests/test_client_view_index.py`

- [ ] **Step 1: Tests:** block absent below threshold; absent for archived/internal; values match bucket; no business names/IDs anywhere in payload (schema whitelist assertion).
- [ ] **Step 2: Implement + surfaces; note in code that Premium gating attaches here once the corepremium plan column exists (comment, not code).**
- [ ] **Step 3: Suite + lint. Commit** — `feat(index): market benchmark line on client view + PDF`

---

### Task 6: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify.
- [ ] Walkthrough: seed ≥3 same-industry clients with scans → recompute → bucket visible in admin, benchmark line on a share view, export CSV contains the bucket; with 2 clients → nothing client-facing.
- [ ] Confirm engagement-letter/T&C note about anonymized benchmarking is flagged to Faris (business task, in PR description). Finish branch.

## Self-review notes

- Spec §1–§4 mapped (model→T1, derivation→T2, job→T3, surfaces→T4–5). Backfill folded into T3's recompute (simpler than a script; spec's intent preserved).
- Defensive `getattr` exclusions honor the index spec's cross-spec dependency note without hard-coupling build order.
- Deviation: admin page placement (gap-matrix section vs new nav entry) deferred to Faris at review because CLAUDE.md §9 locks nav — flagged, default chosen.
