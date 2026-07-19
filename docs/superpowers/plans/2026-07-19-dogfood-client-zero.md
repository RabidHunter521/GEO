# Dogfood: SeenBy as Client #0 (Spec 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One `is_internal` flag on `Client` that keeps SeenBy-as-client-#0 out of every cross-client aggregate, an admin badge/toggle, and the operational runbook doc.

**Architecture:** Column + exclusion filters in `benchmark_service`, `index_service` (if shipped), and portfolio rollups; everything else treats the internal client as a normal client (that's the point of dogfooding).

**Tech Stack:** SQLAlchemy + Alembic, FastAPI, pytest, Next.js.

**Spec:** `docs/superpowers/specs/2026-07-19-dogfood-client-zero-design.md`

## Global Constraints

- Internal client participates in EVERYTHING except cross-client aggregates (benchmark peers, visibility index, portfolio/revenue rollups).
- Public exposure is the existing share view only — no new public page.
- Migration: `down_revision` = single current `alembic heads`. Branch: `feat/dogfood-client-zero` off master.

---

### Task 1: `is_internal` column + migration

**Files:**
- Modify: `backend/app/models/client.py` (after `is_prospect`, mirroring its exact pattern)
- Create: `backend/alembic/versions/<newid>_add_client_is_internal.py`
- Test: `backend/tests/test_client_internal_flag.py`

- [ ] **Step 1: Failing test** — default False roundtrip.

```python
# backend/tests/test_client_internal_flag.py
from app.models.client import Client


def test_is_internal_defaults_false(db):
    c = Client(name="SeenBy", website="https://seenby.my", industry="AI visibility agency")
    db.add(c); db.commit()
    assert db.query(Client).one().is_internal is False
```

- [ ] **Step 2: Run — FAIL. Implement:**

```python
    # Internal client (SeenBy itself as client #0 for dogfooding). Runs like a
    # normal client everywhere EXCEPT cross-client aggregates: benchmark peers,
    # visibility index, portfolio/revenue rollups all exclude it.
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
```

Migration: `op.add_column("clients", sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="false"))`.

- [ ] **Step 3: Run — PASS. Commit** — `feat(dogfood): Client.is_internal flag`

---

### Task 2: Exclusion filters + invariant tests

**Files:**
- Modify: `backend/app/services/benchmark_service.py:50-57` (peer subquery filters — add `Client.is_internal.is_(False)` next to the existing `is_prospect` filter)
- Modify: `backend/app/services/index_service.py` if present (replace the defensive `getattr(c, "is_internal", False)` list-comp with the real column filter)
- Grounding+modify: portfolio/revenue rollups — `grep -rn "is_prospect" backend/app frontend/src` and audit every cross-client aggregation site (the `is_prospect` exclusions mark exactly the places that need an `is_internal` twin: `frontend/src/components/clients/PortfolioSummary.tsx`, gap matrix, any /clients rollup endpoint)
- Test: `backend/tests/test_internal_exclusion.py`

- [ ] **Step 1: Failing tests** — an internal client with the best score in an industry of 3 does not appear in another client's benchmark peers (peer_count == 2 → below MIN_BENCHMARK_PEERS → benchmark None); if index_service exists: internal client's rows contribute to no bucket.

```python
# backend/tests/test_internal_exclusion.py
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.services.benchmark_service import compute_industry_benchmark


def _scored(db, name, score, internal=False):
    c = Client(name=name, website=f"https://{name}.my", industry="dental clinic",
               is_internal=internal)
    db.add(c); db.commit()
    db.add(GeoScore(client_id=c.id, ai_citability=score, brand_authority=0.0,
                    content_quality=0.0, technical_foundations=0.0,
                    structured_data=0.0, overall_score=score))
    db.commit()
    return c


def test_internal_client_is_not_a_benchmark_peer(db):
    a = _scored(db, "a", 50.0)
    _scored(db, "b", 60.0)
    _scored(db, "zero", 99.0, internal=True)
    # only 2 real peers -> below MIN_BENCHMARK_PEERS -> hidden entirely
    assert compute_industry_benchmark(a, db) is None
```

- [ ] **Step 2: Run — FAIL. Implement filters everywhere found in grounding; record the audited list in the commit message.**
- [ ] **Step 3: Full suite. Commit** — `feat(dogfood): internal clients excluded from all cross-client aggregates`

---

### Task 3: Admin UI — badge + settings toggle

**Files:**
- Grounding+modify: settings update schema/route (wherever `is_prospect`/client fields are updated — mirror), `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` (checkbox "Internal client (SeenBy itself)" with helper text), client card/list badge (find where the prospect badge renders on `/clients` and mirror an "Internal" variant)
- Test: extend the clients API test with is_internal update roundtrip

- [ ] Steps: failing API test → backend field → frontend toggle + badge → `rtk lint && rtk tsc --noEmit` → browser-verify → commit — `feat(dogfood): internal badge + settings toggle`

---

### Task 4: Runbook doc

**Files:**
- Create: `docs/dogfood-runbook.md`

- [ ] **Step 1: Write the runbook** with exactly the spec's 5 steps (create client #0 with `is_internal=true`, track rival agencies as competitors, monthly full playbook scan→actions→toolkit→roadmap→publish, share link on marketing site, every papercut = P1 retention bug) plus the 90-day success metric (seen by AI for a "best AI visibility agency Malaysia"-family recommendation query on ≥2 platforms).
- [ ] **Step 2: Commit** — `docs(dogfood): client-zero operational runbook`

---

### Task 5: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify.
- [ ] Walkthrough: create the internal client in the UI, confirm badge, confirm it's absent from portfolio summary numbers and benchmark peers, share link renders.
- [ ] Finish branch.

## Self-review notes

- Spec product scope (flag/exclusions/badge/runbook) fully covered in 4 tasks; nothing else special-cases the internal client (per spec: rough edges must hurt us the way they'd hurt clients).
- Index exclusion is conditional on Spec 4 having shipped; the grep-audit in Task 2 catches it either way.
