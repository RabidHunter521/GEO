# Pitch Mode — Live 3-Query Roast (Spec 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ~60-second, 3-query, 2-platform scan variant runnable live in a sales meeting, with a presentation-grade admin view — stored as a real `Scan` flagged `is_pitch` and excluded from every score/trend/history consumer.

**Architecture:** `Scan.is_pitch` flag + `PITCH_SCAN_RECIPE` constant; a `run_pitch_scan` path that reuses the platform runner but skips scoring, GeoScore creation, alerts, and post-commit heavies; a `/clients/[id]/pitch` presentation route consuming a pitch-results endpoint.

**Tech Stack:** SQLAlchemy + Alembic, FastAPI, Celery (existing scan task pattern), pytest, Next.js.

**Spec:** `docs/superpowers/specs/2026-07-19-pitch-mode-design.md`

## Global Constraints

- Recipe: 1 recommendation + 1 local + 1 brand query on `("chatgpt", "gemini")` ∩ enabled platforms — in `PITCH_SCAN_RECIPE`, never hardcoded in the service.
- Pitch scans create NO GeoScore, fire NO alerts, trigger NO action center / provenance / remediation post-commit steps.
- Every consumer that queries `Scan` for "latest completed" or history must add `is_pitch == False` (invariant tests).
- Admin-only; competitor names NOT redacted on the pitch view; verdict copy is deterministic ("Seen by AI" / "Not seen by AI").
- Migration: `down_revision` = single current `alembic heads`. Branch: `feat/pitch-mode` off master.

---

### Task 1: `is_pitch` flag + recipe constant + migration

**Files:**
- Modify: `backend/app/models/scan.py` (add `is_pitch`)
- Modify: `backend/app/core/constants.py`
- Create: `backend/alembic/versions/<newid>_add_scan_is_pitch.py`
- Modify: `backend/tests/conftest.py` only if model imports change (they don't — scan already registered)
- Test: `backend/tests/test_pitch_flag.py`

**Interfaces:**
- Produces: `Scan.is_pitch: bool` (server_default false);

```python
# constants.py
# Pitch mode: minimal live-demo scan. (category, platforms) — queries are the
# FIRST template of each category from QUERY_TEMPLATES, platforms intersected
# with the client's enabled set.
PITCH_SCAN_CATEGORIES: Final = ("recommendation", "local", "brand")
PITCH_SCAN_PLATFORMS: Final = ("chatgpt", "gemini")
```

- [ ] **Step 1: Failing test** — `is_pitch` defaults False.
- [ ] **Step 2: Implement column (mirror `is_control` pattern: `Boolean, nullable=False, default=False, server_default="false"`), constants, migration.**
- [ ] **Step 3: Run — PASS. `alembic heads` single head. Commit** — `feat(pitch): Scan.is_pitch + recipe constants`

---

### Task 2: `build_pitch_queries` + `run_pitch_scan`

**Files:**
- Modify: `backend/app/services/query_builder.py` (add `build_pitch_queries`)
- Modify: `backend/app/services/scan_service.py` (add `run_pitch_scan`; extract row-creation reuse where trivial, otherwise keep a small parallel loop — pitch runs are 6 calls, simplicity beats DRY here)
- Test: `backend/tests/test_pitch_scan.py`

**Interfaces:**
- Consumes: `QUERY_TEMPLATES`, `_location`/`_locality`, `detect_brand_mention`, `get_platform_client`, `PITCH_SCAN_CATEGORIES/PLATFORMS`, `_enabled_platforms`.
- Produces:
  - `build_pitch_queries(client, competitors) -> list[dict]` — first template per recipe category, same dict shape; `local`/`recommendation` skipped when no location (mirroring `build_client_queries` — a pitch for a location-less client degrades to brand-only, never "in None").
  - `run_pitch_scan(scan_id, db) -> None` — same status lifecycle (`running`→`completed`/`failed`), per-platform isolation, cost logging via `record_llm_usage`, but: only recipe platforms ∩ enabled; NO GeoScore, NO alerts, NO action center, NO provenance enrichment, NO remediation sync, NO position extraction.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_pitch_scan.py
from unittest.mock import MagicMock, patch
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.services.query_builder import build_pitch_queries
from app.services.scan_service import run_pitch_scan


def test_build_pitch_queries_recipe(db):
    c = Client(name="Klinik A", website="https://a.my", industry="dental clinic", city="KL")
    built = build_pitch_queries(c, [])
    assert [q["category"] for q in built] == ["recommendation", "local", "brand"]
    assert "dental clinic" in built[0]["query_text"]


def test_build_pitch_queries_no_location_degrades_to_brand(db):
    c = Client(name="Klinik A", website="https://a.my", industry="dental clinic")
    assert [q["category"] for q in build_pitch_queries(c, [])] == ["brand"]


def _mock_platform():
    pc = MagicMock()
    pc.query.return_value = MagicMock(text="Klinik B is the best choice", citations=[],
                                      model="m", input_tokens=1, output_tokens=1)
    return pc


def test_run_pitch_scan_creates_flagged_rows_and_no_geoscore(db):
    c = Client(name="Klinik A", website="https://a.my", industry="dental clinic", city="KL")
    db.add(c); db.commit()
    scan = Scan(client_id=c.id, is_pitch=True); db.add(scan); db.commit()
    with patch("app.services.scan_service.get_platform_client", return_value=_mock_platform()):
        run_pitch_scan(scan.id, db)
    db.refresh(scan)
    assert scan.status == "completed"
    rows = db.query(ScanQueryResult).all()
    assert len(rows) == 6  # 3 queries x 2 platforms
    assert db.query(GeoScore).count() == 0
```

- [ ] **Step 2: Run — FAIL. Implement.** `build_pitch_queries`:

```python
def build_pitch_queries(client, competitors: list) -> list[dict]:
    """Pitch mode: one query per recipe category (first template), same shape
    as build_client_queries. Location-dependent categories degrade away."""
    from app.core.constants import PITCH_SCAN_CATEGORIES, QUERY_TEMPLATES
    location, locality = _location(client), _locality(client)
    out: list[dict] = []
    for category in PITCH_SCAN_CATEGORIES:
        template = QUERY_TEMPLATES[category][0]
        if category == "brand":
            text = template.format(brand=client.name)
        elif category == "recommendation":
            if not location:
                continue
            text = _dedupe_adjacent_words(template.format(industry=client.industry, location=location))
        elif category == "local":
            if not locality:
                continue
            text = _dedupe_adjacent_words(template.format(industry=client.industry, city=locality))
        else:
            continue
        out.append({"category": category, "query_text": text, "competitor_id": None})
    return out
```

`run_pitch_scan`: mirror `run_scan`'s skeleton (idempotency guard, status transitions, ThreadPoolExecutor over `[p for p in PITCH_SCAN_PLATFORMS if p in _enabled_platforms(client)]`, per-platform try/except, `record_llm_usage`, final commit + ActivityLog `event_type="pitch_scan_completed"`), with a simplified per-platform runner that loops `build_pitch_queries` and creates `ScanQueryResult(..., brand_detected=detect_brand_mention(text, client.name))` rows — no positions, no sources. The except-branch marks failed exactly like `run_scan`.

- [ ] **Step 3: Run — PASS. Commit** — `feat(pitch): pitch query builder + fast scan path`

---

### Task 3: The `is_pitch` exclusion invariant

**Files:**
- Modify (each gains `Scan.is_pitch.is_(False)` on their latest/history scan queries): `backend/app/services/digest_service.py:108-117,129-138`, `backend/app/services/win_loss_service.py:36-41`, `backend/app/services/remediation_service.py:36-41`, `backend/app/services/headline_battle_service.py` (its scan lookup), `backend/app/services/scan_diff_service.py`, `backend/app/services/gap_matrix_service.py`, `backend/app/services/competitor_intelligence_service.py`, `backend/app/services/report_service.py` (scan-history gathering), `backend/app/api/v1/client_view.py` (trend/overview scan queries), `backend/app/services/causality_service.py` (if Spec 1 shipped), `backend/app/services/index_service.py` (if Spec 4 shipped — already defensive)
- Grounding: `grep -rn "status == \"completed\"" backend/app | grep -v test` — every hit is a candidate; audit all, record the list in the commit message. Admin scan LIST endpoints keep pitch scans, labeled.
- Test: `backend/tests/test_pitch_exclusion.py`

- [ ] **Step 1: Failing tests** — after a pitch scan (newer than a real scan): `compute_win_loss` still reads the real scan; digest `_compute_digest_data` uses the real scan's results; client-view trend length unchanged.
- [ ] **Step 2: Implement filters. Run full suite. Commit** — `feat(pitch): pitch scans invisible to every score/trend/history consumer`

---

### Task 4: Pitch endpoint + Celery task

**Files:**
- Modify: `backend/app/api/v1/scans.py` — `POST /clients/{client_id}/scans/pitch` (creates `Scan(is_pitch=True)`, dispatches; mirror the existing scan-trigger route incl. `has_active_scan` guard) and `GET /scans/{scan_id}/pitch-results` (rows with query, platform label, verdict, response excerpt + detected competitor names via `detect_brand_mention` against the client's competitors — admin surface, response_text excerpt allowed; cap excerpt ~600 chars)
- Modify: `backend/workers/tasks/scan_tasks.py` — thin `run_pitch_scan_task` mirroring the existing scan task
- Create: `backend/app/schemas/pitch.py`
- Test: `backend/tests/test_api_pitch.py`

- [ ] **Step 1: API tests** — trigger creates flagged scan; results endpoint returns per-query verdicts + competitor hits; closing summary counts (`rival_seen_count`, `client_seen_count`, `total`).
- [ ] **Step 2: Implement. Run. Commit** — `feat(pitch): trigger + results endpoints and worker task`

---

### Task 5: Presentation route `/clients/[id]/pitch`

**Files:**
- Create: `frontend/src/app/clients/[id]/pitch/page.tsx` + `PitchClient.tsx`
- Modify: `frontend/src/lib/api.ts`, `frontend/src/types/index.ts`
- Modify: CLAUDE.md §9 nav table (add `/clients/[id]/pitch → live pitch mode (admin sales tool)`) — same commit
- Modify: `frontend/src/app/clients/[id]/scan/ScanClient.tsx` — label pitch scans in any scan list it renders ("Pitch demo — not scored")

**Interfaces:**
- Consumes: Task 4 endpoints; existing scan status polling helper in `api.ts` (grounding: reuse whatever `ScanClient.tsx` polls with).

- [ ] **Step 1: Build the three states:** run state (big "Run live scan" button → trigger + poll, per-query progress ticks), result state (one full-screen card per query: query as asked, platform chip, verdict badge — reuse `VisibilityBadge` component idiom — verbatim excerpt with client brand highlighted green / competitor names highlighted amber via a deterministic `<mark>` split on detected names; keyboard ←/→ navigation), closing card ("{Rival} was seen by AI {n} of {total} times. {Client} was seen {m} of {total}." + "present latest results" shortcut when a completed pitch or full scan exists).
- [ ] **Step 2: `rtk lint && rtk tsc --noEmit`; browser-verify with a seeded prospect end-to-end (mocked platforms acceptable); screenshot the result state for the PR.**
- [ ] **Step 3: Commit** — `feat(pitch): presentation route + nav update`

---

### Task 6: Final verification gate

- [ ] Full suite; `alembic heads` single head; seenby-verify.
- [ ] Walkthrough per spec success criterion: blank prospect → pitch page → run → rival-on-screen; then run a REAL scan and confirm score history/trends contain only the real scan.
- [ ] Finish branch.

## Self-review notes

- Spec's backend/frontend/flow sections map to T1–T5; alert/action-center/provenance skips are structural (run_pitch_scan never calls them) rather than flag-guards — simpler and safer than the spec's "guard" wording, same outcome (documented deviation).
- "Present latest results" fallback included (T5) per spec's live-demo risk mitigation.
- Pitch scans excluded from Spec 4's index via that plan's defensive filter; T3's audit double-covers.
