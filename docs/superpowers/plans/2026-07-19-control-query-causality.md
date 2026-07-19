# Control-Query Causal Proof (Spec 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track admin-defined benchmark queries that SeenBy deliberately does NOT optimize, run them on every scan, exclude them from every score/analysis surface, and chart optimized-vs-control visibility over time as causal proof.

**Architecture:** New `ControlQuery` model + `is_control` flag on `ScanQueryResult`; the scan engine appends active controls per platform; a hard exclusion invariant is added to every aggregating consumer; a compute-on-read `causality_service` produces the two-series trend for admin scan page, monthly PDF, and client view.

**Tech Stack:** SQLAlchemy + Alembic (RLS per seenby-migrations), FastAPI, pytest, Next.js.

**Spec:** `docs/superpowers/specs/2026-07-19-control-query-causality-design.md`

## Global Constraints

- `MAX_CONTROL_QUERIES = 5` per client (constant).
- Control rows NEVER influence: GEO score, win/loss, gap matrix, competitor intelligence, proof cards, action center, content roadmap inputs, alerts, remediation sync, benchmark/index aggregates. Each consumer gets an invariant regression test.
- Client-facing copy: "queries we optimized" vs "queries we left alone" — never "control group"; CLAUDE.md §2 vocabulary throughout.
- Client-view chart renders only with ≥2 scans of control history.
- No SCORE_VERSION bump (score formula unchanged — controls are excluded, not weighted).
- Migration: follow seenby-migrations skill; set `down_revision` to the SINGLE current `alembic heads` output at implementation time (verify — a past revision-ID collision broke `alembic heads` before).
- Branch: `feat/control-query-causality` off master. Tests: `cd backend && python -m pytest <file> -v`.

---

### Task 1: `ControlQuery` model + `is_control` column + migration

**Files:**
- Create: `backend/app/models/control_query.py`
- Modify: `backend/app/models/scan_query_result.py` (add `is_control`)
- Modify: `backend/tests/conftest.py` (model import list — add `control_query`)
- Create: `backend/alembic/versions/<newid>_add_control_queries.py`
- Modify: `backend/app/core/constants.py` (add `MAX_CONTROL_QUERIES`)
- Test: `backend/tests/test_control_query_model.py`

**Interfaces:**
- Produces: `ControlQuery(id, client_id, query_text, category, active, created_at)`; `ScanQueryResult.is_control: bool` (server_default false); `MAX_CONTROL_QUERIES: Final = 5`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_control_query_model.py
import uuid
from app.models.client import Client
from app.models.control_query import ControlQuery
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult


def _client(db):
    c = Client(name="Clinic A", website="https://a.my", industry="dental clinic")
    db.add(c); db.commit()
    return c


def test_control_query_roundtrip(db):
    c = _client(db)
    cq = ControlQuery(client_id=c.id, query_text="Best physio in Penang", category="recommendation")
    db.add(cq); db.commit()
    row = db.query(ControlQuery).one()
    assert row.active is True
    assert row.query_text == "Best physio in Penang"


def test_scan_query_result_is_control_defaults_false(db):
    c = _client(db)
    s = Scan(client_id=c.id); db.add(s); db.commit()
    r = ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation", query_text="q")
    db.add(r); db.commit()
    assert db.query(ScanQueryResult).one().is_control is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_control_query_model.py -v`
Expected: FAIL — `ModuleNotFoundError: app.models.control_query`

- [ ] **Step 3: Implement model + column + constant**

```python
# backend/app/models/control_query.py
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ControlQuery(Base):
    """An admin-defined benchmark query SeenBy deliberately does NOT optimize.

    Run on every scan alongside the standard set (result rows carry
    is_control=True) but excluded from the GEO score and every analysis
    surface — it exists only to prove causation: optimized queries move,
    untouched ones don't. Deactivate (never delete) when the retainer starts
    touching a control's topic, so history stays intact.
    """

    __tablename__ = "control_queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="recommendation")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

In `scan_query_result.py` add after `recommendation_position` (line 27):

```python
    # Benchmark row from a ControlQuery — excluded from score and all analysis
    # surfaces; exists only for the optimized-vs-untouched causal comparison.
    is_control: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
```

In `constants.py` after `MAX_COMPETITORS`:

```python
MAX_CONTROL_QUERIES: Final = 5
```

Add `control_query` to the conftest model-import line.

- [ ] **Step 4: Migration**

Run `cd backend && python -m alembic heads` — MUST print exactly one head; use it as `down_revision`. Create `backend/alembic/versions/<12hex>_add_control_queries.py` following the pattern of `2a685d803d33_create_scan_query_sources_table.py` (RLS enabled inline on the new table, per seenby-migrations):

```python
"""add control_queries table and scan_query_results.is_control

Revision ID: <newid>
Revises: <current head>
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "<newid>"
down_revision = "<current head — from `alembic heads`>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="recommendation"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE control_queries ENABLE ROW LEVEL SECURITY")
    op.add_column("scan_query_results",
                  sa.Column("is_control", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("scan_query_results", "is_control")
    op.drop_table("control_queries")
```

- [ ] **Step 5: Run tests, then commit**

Run: `cd backend && python -m pytest tests/test_control_query_model.py -v` — PASS.
Run: `cd backend && python -m alembic heads` — still exactly one head.

```bash
git add backend/app/models/control_query.py backend/app/models/scan_query_result.py backend/app/core/constants.py backend/tests/conftest.py backend/tests/test_control_query_model.py backend/alembic/versions/
git commit -m "feat(control): ControlQuery model + is_control result flag"
```

---

### Task 2: Scan engine runs active controls per platform

**Files:**
- Modify: `backend/app/services/query_builder.py` (add `build_control_queries`)
- Modify: `backend/app/services/scan_service.py:110-188` (`_run_platform_queries`) and `run_scan` (~line 208, competitor load)
- Test: `backend/tests/test_scan_control_queries.py`

**Interfaces:**
- Consumes: `ControlQuery` (Task 1).
- Produces: `build_control_queries(control_queries) -> list[dict]` (same `{category, query_text, competitor_id}` shape as `build_client_queries`, plus `is_control: True`); `_run_platform_queries(platform, platform_client, scan, client, competitors, control_queries)` — new last parameter.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scan_control_queries.py
import uuid
from unittest.mock import MagicMock
from app.models.client import Client
from app.models.control_query import ControlQuery
from app.models.scan import Scan
from app.services.query_builder import build_control_queries
from app.services.scan_service import _run_platform_queries
from app.core.constants import MAX_CONTROL_QUERIES


def test_build_control_queries_shape_and_cap():
    controls = [
        ControlQuery(client_id=uuid.uuid4(), query_text=f"q{i}", category="recommendation", active=True)
        for i in range(7)
    ]
    built = build_control_queries(controls)
    assert len(built) == MAX_CONTROL_QUERIES  # capped defensively
    assert all(q["is_control"] for q in built)
    assert built[0]["competitor_id"] is None


def test_platform_run_marks_control_rows(db):
    client = Client(name="Clinic A", website="https://a.my", industry="dental clinic", city="KL")
    db.add(client); db.commit()
    scan = Scan(client_id=client.id); db.add(scan); db.commit()
    controls = [ControlQuery(client_id=client.id, query_text="Best physio in Penang",
                             category="recommendation", active=True)]
    pc = MagicMock()
    pc.query.return_value = MagicMock(text="Some answer", citations=[], model="m",
                                      input_tokens=1, output_tokens=1)
    results, _ = _run_platform_queries("chatgpt", pc, scan, client, [], controls)
    control_rows = [r for r in results if r.is_control]
    assert len(control_rows) == 1
    assert control_rows[0].query_text == "Best physio in Penang"
    assert all(not r.is_control for r in results if r.query_text != "Best physio in Penang")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_scan_control_queries.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_control_queries'`

- [ ] **Step 3: Implement**

`query_builder.py` (bottom):

```python
def build_control_queries(control_queries) -> list[dict]:
    """Benchmark queries the retainer deliberately leaves alone. Text is used
    verbatim (admin-authored, no templating). Defensively capped."""
    from app.core.constants import MAX_CONTROL_QUERIES
    active = [cq for cq in control_queries if cq.active][:MAX_CONTROL_QUERIES]
    return [
        {"category": cq.category, "query_text": cq.query_text,
         "competitor_id": None, "is_control": True}
        for cq in active
    ]
```

`scan_service.py`: add parameter `control_queries: list` to `_run_platform_queries` (after `competitors`). After the client-query loop (line 169) and before the competitor loop, add:

```python
    for q in build_control_queries(control_queries):
        result = platform_client.query(q["query_text"])
        usages.append(result)
        results.append(ScanQueryResult(
            scan_id=scan.id,
            platform=platform,
            competitor_id=None,
            category=q["category"],
            query_text=q["query_text"],
            response_text=result.text,
            brand_detected=detect_brand_mention(result.text, client.name),
            is_control=True,
        ))
        time.sleep(_INTER_QUERY_DELAY_SECONDS)
```

(no position extraction, no provenance capture for control rows — measurement only). In `run_scan`, alongside the competitor load (~line 209):

```python
        control_queries = (
            db.query(ControlQuery)
            .filter(ControlQuery.client_id == scan.client_id, ControlQuery.active.is_(True))
            .all()
        )
```

…and pass `control_queries` through the `pool.submit(_run_platform_queries, platform, pc, scan, client, competitors, control_queries)` call. Import `ControlQuery` and `build_control_queries` at the top.

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_scan_control_queries.py tests/ -k "scan" -v`
Expected: PASS incl. pre-existing scan tests (their `_run_platform_queries` callers must be updated to pass `[]` — fix any that break).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/query_builder.py backend/app/services/scan_service.py backend/tests/test_scan_control_queries.py
git commit -m "feat(control): scan engine runs active control queries per platform"
```

---

### Task 3: The exclusion invariant — every consumer ignores control rows

**Files:**
- Modify: `backend/app/services/scoring_service.py:12,39` (filter in `compute_platform_breakdown` and the legacy path of `compute_ai_citability`)
- Modify: `backend/app/services/win_loss_service.py:48-57` (add filter)
- Modify: `backend/app/services/digest_service.py:147-154` (`client_results` query — add filter)
- Modify: `backend/app/services/remediation_service.py:44-52` (hallucination keys query — add filter)
- Grounding+modify: `backend/app/services/gap_matrix_service.py`, `backend/app/services/competitor_intelligence_service.py`, `backend/app/services/scan_diff_service.py`, `backend/app/services/proof_card_service.py` callers, `backend/app/services/report_service.py` result queries, `backend/app/api/v1/scans.py` results listing (admin page may SHOW controls, distinctly labeled — only aggregations must exclude)
- Test: `backend/tests/test_control_exclusion.py`

**Interfaces:**
- Consumes: `is_control` (Task 1). No new interfaces produced — this task is pure filtering.

- [ ] **Step 1: Grounding sweep**

Run: `cd backend && grep -rn "ScanQueryResult" app/services app/api | grep -v test` and list every site that filters/aggregates result rows. For each, decide: aggregation (exclude controls) vs raw admin listing (keep, label). Record the list in the commit message.

- [ ] **Step 2: Write the failing invariant tests**

```python
# backend/tests/test_control_exclusion.py
"""THE invariant: a control row changes nothing outside the causal chart."""
import uuid
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.scoring_service import compute_ai_citability, compute_platform_breakdown
from app.services.win_loss_service import compute_win_loss


def _seed(db, with_control):
    c = Client(name="Clinic A", website="https://a.my", industry="dental clinic")
    db.add(c); db.commit()
    s = Scan(client_id=c.id, status="completed")
    from datetime import datetime
    s.completed_at = datetime.utcnow()
    db.add(s); db.commit()
    rows = [ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                            query_text="best dental clinic in KL", response_text="Clinic A is great",
                            brand_detected=True)]
    if with_control:
        rows.append(ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                                    query_text="best physio in Penang", response_text="others",
                                    brand_detected=False, is_control=True))
    db.add_all(rows); db.commit()
    return c, s, rows


def test_citability_identical_with_and_without_control(db):
    c, s, rows = _seed(db, with_control=True)
    bd = compute_platform_breakdown(rows)
    assert bd["chatgpt"]["queries"] == 1  # control excluded
    assert compute_ai_citability(rows, bd) == 100.0
    assert compute_ai_citability([r for r in rows if not r.is_control]) == 100.0


def test_win_loss_ignores_control_rows(db):
    c, s, rows = _seed(db, with_control=True)
    wl = compute_win_loss(c.id, db)
    assert all(e.query_text != "best physio in Penang" for e in wl.entries)
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_control_exclusion.py -v`
Expected: FAIL — breakdown counts 2 queries.

- [ ] **Step 4: Implement the filters**

`scoring_service.compute_platform_breakdown` line 12 becomes:

```python
    client_results = [
        r for r in query_results
        if r.competitor_id is None and not getattr(r, "is_control", False)
    ]
```

Same list-comprehension change in `compute_ai_citability`'s legacy path (line 39). `win_loss_service.compute_win_loss` query gains `.filter(ScanQueryResult.is_control.is_(False))`. `digest_service` `client_results` query gains the same filter. `remediation_service._current_hallucination_keys` gains the same filter. Apply the identical `.filter(ScanQueryResult.is_control.is_(False))` (or list-comp `not r.is_control`) to every aggregation site found in Step 1. For the admin scan-results listing in `api/v1/scans.py`, KEEP control rows but add `is_control` to the response schema so the UI can label them "benchmark — left alone".

- [ ] **Step 5: Run full suite, commit**

Run: `cd backend && python -m pytest -q`
Expected: PASS.

```bash
git add -A backend
git commit -m "feat(control): exclusion invariant — control rows never touch score/analysis"
```

---

### Task 4: `causality_service` + history endpoint

**Files:**
- Create: `backend/app/services/causality_service.py`
- Modify: `backend/app/api/v1/scans.py` (add `GET /clients/{client_id}/causality`) — follow the existing route/service split
- Create: `backend/app/schemas/causality.py`
- Test: `backend/tests/test_causality_service.py`

**Interfaces:**
- Produces: `compute_causal_trend(client_id, db) -> CausalTrend` where `CausalTrend(points: list[CausalPoint])`, `CausalPoint(scan_id, completed_at, optimized_frequency: float | None, control_frequency: float | None)`. Frequencies are percentages over client-owned rows of completed, non-pitch scans; `control_frequency` None when the scan had no control rows.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_causality_service.py
from datetime import datetime, timedelta
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.causality_service import compute_causal_trend


def _scan(db, client, days_ago, opt_seen, opt_total, ctl_seen, ctl_total):
    s = Scan(client_id=client.id, status="completed")
    s.completed_at = datetime.utcnow() - timedelta(days=days_ago)
    db.add(s); db.commit()
    rows = []
    for i in range(opt_total):
        rows.append(ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                                    query_text=f"opt{i}", brand_detected=i < opt_seen))
    for i in range(ctl_total):
        rows.append(ScanQueryResult(scan_id=s.id, platform="chatgpt", category="recommendation",
                                    query_text=f"ctl{i}", brand_detected=i < ctl_seen, is_control=True))
    db.add_all(rows); db.commit()
    return s


def test_two_series_split(db):
    c = Client(name="A", website="https://a.my", industry="x"); db.add(c); db.commit()
    _scan(db, c, 30, opt_seen=2, opt_total=4, ctl_seen=1, ctl_total=2)
    _scan(db, c, 1, opt_seen=3, opt_total=4, ctl_seen=1, ctl_total=2)
    trend = compute_causal_trend(c.id, db)
    assert len(trend.points) == 2
    assert trend.points[0].optimized_frequency == 50.0
    assert trend.points[1].optimized_frequency == 75.0
    assert trend.points[0].control_frequency == 50.0
    assert trend.points[1].control_frequency == 50.0


def test_no_control_rows_yields_none_frequency(db):
    c = Client(name="A", website="https://a.my", industry="x"); db.add(c); db.commit()
    _scan(db, c, 1, opt_seen=1, opt_total=2, ctl_seen=0, ctl_total=0)
    trend = compute_causal_trend(c.id, db)
    assert trend.points[0].control_frequency is None
```

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# backend/app/services/causality_service.py
"""Optimized-vs-control visibility trend — the causal proof chart.

Pure compute-on-read over stored booleans (survives the 90-day raw-response
purge). Client-facing label: "queries we optimized" vs "queries we left
alone" — never "control group"."""
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult


@dataclass
class CausalPoint:
    scan_id: uuid.UUID
    completed_at: datetime
    optimized_frequency: float | None
    control_frequency: float | None


@dataclass
class CausalTrend:
    points: list[CausalPoint]


def _freq(rows) -> float | None:
    if not rows:
        return None
    return round(sum(1 for r in rows if r.brand_detected) / len(rows) * 100, 2)


def compute_causal_trend(client_id: uuid.UUID, db: Session) -> CausalTrend:
    scans = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at)
        .all()
    )
    points: list[CausalPoint] = []
    for scan in scans:
        rows = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == scan.id,
                ScanQueryResult.competitor_id.is_(None),
            )
            .all()
        )
        optimized = [r for r in rows if not r.is_control]
        controls = [r for r in rows if r.is_control]
        points.append(CausalPoint(
            scan_id=scan.id,
            completed_at=scan.completed_at,
            optimized_frequency=_freq(optimized),
            control_frequency=_freq(controls),
        ))
    return CausalTrend(points=points)
```

Schema + route: `schemas/causality.py` with Pydantic mirrors (`CausalityPointResponse`, `CausalityResponse`); route in `api/v1/scans.py` following the file's existing admin-route pattern, serializing the dataclasses. If a Spec-6 `is_pitch` column exists by implementation time, add `Scan.is_pitch.is_(False)` to the scan filter (note in code comment either way).

- [ ] **Step 4: Run tests, commit**

```bash
git add backend/app/services/causality_service.py backend/app/schemas/causality.py backend/app/api/v1/scans.py backend/tests/test_causality_service.py
git commit -m "feat(control): causal trend service + admin history endpoint"
```

---

### Task 5: Control CRUD API + admin settings UI

**Files:**
- Modify: `backend/app/api/v1/clients.py` (or the settings-adjacent router — grounding: find where competitors CRUD lives and mirror it): `GET/POST /clients/{id}/control-queries`, `PATCH /clients/{id}/control-queries/{cq_id}` (deactivate/reactivate only — no delete)
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`
- Modify: `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` (new "Benchmark queries we leave alone" card; mirror the existing list-edit patterns in that file)
- Test: `backend/tests/test_api_control_queries.py`

**Interfaces:**
- Consumes: `ControlQuery`, `MAX_CONTROL_QUERIES`.
- Produces: REST endpoints; POST rejects when active count would exceed `MAX_CONTROL_QUERIES` (HTTP 422 with message "Maximum 5 benchmark queries per client").

- [ ] **Step 1: Backend test** — create/list/deactivate roundtrip + cap rejection + 404 on foreign client id (write in the style of `backend/tests/test_api_provenance.py`, which shows the app/client fixture pattern for API tests).
- [ ] **Step 2: Verify failure, implement routes** (thin routes; logic in a small `control_query_service.py` if the router file's conventions demand it — mirror competitors CRUD).
- [ ] **Step 3: Frontend: api.ts functions (`getControlQueries`, `createControlQuery`, `deactivateControlQuery`), types, settings card with the guardrail helper text from the spec: "Pick queries the retainer will NOT touch. If we later work on one, deactivate it."
- [ ] **Step 4: `cd backend && python -m pytest -q` + `cd frontend && rtk lint && rtk tsc --noEmit` — PASS. Browser-verify add/deactivate in settings.**
- [ ] **Step 5: Commit** — `feat(control): admin CRUD + settings card for benchmark queries`

---

### Task 6: Surfaces — admin chart, client-view chart, PDF section

**Files:**
- Create: `frontend/src/components/clients/CausalTrendChart.tsx` (two-line chart; reuse the charting approach of `frontend/src/components/competitors/VisibilityTrendChart.tsx` — read it first and mirror its props/format)
- Modify: `frontend/src/app/clients/[id]/scan/ScanClient.tsx` (add "Proof of impact" panel when ≥1 point has control data)
- Modify: `backend/app/api/v1/client_view.py` — extend the overview response with an optional `causal_trend` block (whitelisted: dates + two frequency arrays only), present only when ≥2 points have non-None `control_frequency`
- Modify: `frontend/src/app/view/[token]/page.tsx` — render the chart with heading "Queries we optimized vs. queries we left alone"
- Modify: `backend/app/services/report_service.py` — new "Did our work cause this?" section; grounding: locate `_gather_report_data` (~line 810 region) and the section-builder pattern (e.g. `_build_battle_html` ~885–907), mirror it; deterministic sentence exactly per spec: `"Queries we worked on: seen by AI {a}% of the time, up from {b}%. Queries we left alone: {c}%, up from {d}%."` using first-vs-latest points (omit section when <2 control points)
- Test: `backend/tests/test_client_view_causality.py` + extend report tests

**Interfaces:**
- Consumes: `compute_causal_trend` (Task 4).
- Produces: `ClientViewCausalTrend` Pydantic schema `{dates: list[str], optimized: list[float | None], left_alone: list[float | None]}`.

- [ ] **Step 1: Backend test — client-view gate:** overview payload lacks `causal_trend` with 0/1 control-bearing scans; contains it with 2; no `response_text` or internal fields (schema whitelist test mirroring existing client_view tests).
- [ ] **Step 2: Implement backend block + schema; run tests.**
- [ ] **Step 3: Frontend chart component + both placements; PDF section; `rtk lint`, `rtk tsc --noEmit`, backend suite.**
- [ ] **Step 4: Language check — grep the diff for banned vocabulary (`cited`, `citation rate`, `control group` on client surfaces).**
- [ ] **Step 5: Commit** — `feat(control): causal proof chart on admin, client view, and PDF`

---

### Task 7: Final verification gate

- [ ] `cd backend && python -m pytest -q` — full suite green.
- [ ] Run seenby-verify skill; live walkthrough: seed a client, add 2 controls, run a (mocked or real) scan, confirm: controls appear labeled on the admin scan page, excluded from score, chart renders after second scan, client view hides chart until 2 control points.
- [ ] `alembic heads` — exactly one head. Commit fixes; finish branch per superpowers:finishing-a-development-branch.

## Self-review notes

- Spec §1–§5 all mapped (model→T1, engine→T2, invariant→T3, chart→T4/T6, UI→T5).
- Deviation: admin scan-results listing keeps control rows visible (labeled) — spec's "measurement-only" invariant concerns aggregations, and hiding rows from the admin would hurt operability. Documented in T3.
- Spec's "deactivated controls drop out of the series from that date": v1 computes per-scan from stored rows, so a deactivated control simply stops appearing in future scans — historical points keep it. Matches intent; no extra dating logic needed.
