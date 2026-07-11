# Share-of-Source Trend + Flip Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a Share-of-Source snapshot on every completed scan and auto-detect verified "citation flips" (a source that used to cite only a competitor now cites the client too), so the admin gets a trend line and an automatic win signal instead of a single recompute-on-read snapshot.

**Architecture:** Refactor the existing `provenance_service.compute_share_of_source` into two reusable pure pieces (`_collect_sources`, `_summarize`), add a new persistence + flip-detection entrypoint (`compute_and_persist_snapshot`) called from `scan_service.run_scan`'s existing post-commit best-effort block, and add one new read endpoint for the trend history. A new `ShareOfSourceSnapshot` model/table stores one row per completed scan.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend/app), pytest, Next.js 15 + TypeScript + Tailwind/shadcn (frontend/src), no new dependencies.

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-10-share-of-source-trend-flip-detection-design.md` ("Status: Approved for planning"). Follow its locked decisions in §2 exactly; deviations found while grounding this plan in the real code are called out per-task below with the reason.
- Perplexity-only, v1 scope — inherited from the underlying provenance feature. No new platforms.
- No new scheduling — the snapshot is computed inline in the existing on-demand scan flow only (CLAUDE.md §11: scans are on-demand only).
- Every new post-commit step must be best-effort and isolated: on failure, `db.rollback()`, log, swallow — never undo the scan itself (CLAUDE.md §10, and the existing pattern at every other post-commit step in `scan_service.run_scan`).
- No backfill of snapshots for scans that ran before this ships.
- No client-facing surface in this feature (admin-only trend + activity log). CLAUDE.md §2 language rules still apply to the one new client-facing string this touches: none — the flip event is an internal `ActivityLog` note, not client-facing copy, so the §2 table doesn't constrain its wording, but keep it factual and consistent with the rest of the admin activity log.
- Extend existing test files, don't create parallel ones, per `seenby-workflow`: `backend/tests/test_provenance_share.py`, `backend/tests/test_scan_service.py`, `backend/tests/test_api_provenance.py`.
- Run `seenby-verify` before calling this done (pytest, frontend typecheck+build, banned-language grep, alembic heads sanity).

## Plan-vs-spec deviations found while grounding this in the real code

1. **A genuine pre-existing bug blocks this plan and must be fixed first (Task 1).** Two Alembic migration files both declare `revision = 'a1b2c3d4e5f6'`: `a1b2c3d4e5f6_create_action_recommendations_table.py` (2026-06-10, down_revision `f8a9b0c1d2e3`) and `a1b2c3d4e5f6_enable_rls_scan_query_sources.py` (2026-07-08, down_revision `2a685d803d33`, currently untracked in git). This makes `alembic heads` raise `CycleDetected` — there is no valid single head to build a new migration on top of. This is unrelated to Share-of-Source but has to be fixed before any new migration can be added safely, so it's Task 1.
2. **The spec's §7 read-API section names the existing live endpoint `GET /clients/{client_id}/competitors/share-of-source`.** The endpoint that actually shipped is `GET /clients/{client_id}/competitors/provenance` (see `backend/app/api/v1/competitors.py:63-70`, function `get_provenance`). The spec's path name was aspirational/mistaken, not what's deployed. This plan adds the new history endpoint as `GET /clients/{client_id}/competitors/provenance/history` — a sibling of the real existing path — and leaves the existing `/provenance` route byte-for-byte unchanged, which satisfies the spec's actual intent ("unchanged, zero behavior change, zero risk to the shipped feature").
3. **`_collect_sources`'s spec signature is `(scan_id, client_id, db)`.** `client_id` is redundant: the query already scopes to `scan_id` via the `ScanQueryResult.scan_id == scan_id` filter, and a scan belongs to exactly one client. This plan drops the unused parameter — `_collect_sources(scan_id, db)` — matching the sibling function `enrich_scan_sources(scan_id, db)` in the same file, which has the same shape. `client_id` is still passed explicitly to `compute_and_persist_snapshot` (needed there, to stamp the snapshot row) and to `_summarize` (needed there, to look up competitors/client).
4. **Counts are folded into the `unique` dict instead of a parallel `counts` dict**, as `{"domain": ..., "title": ..., "present": ..., "count": ...}` — this is what the spec means by "keeps the `unique` dict ... in memory" for flip detection (§5), and it's a strict simplification of the current two-dict implementation, not a behavior change.

---

### Task 1: Fix the Alembic revision-ID collision (prerequisite)

**Files:**
- Rename: `backend/alembic/versions/a1b2c3d4e5f6_create_action_recommendations_table.py` → `backend/alembic/versions/c9d1e2f3a4b5_create_action_recommendations_table.py`
- Modify: `backend/alembic/versions/b2c3d4e5f6a7_add_manual_score_evidence_to_clients.py`

**Interfaces:**
- Produces: a single unambiguous Alembic head, `a1b2c3d4e5f6` (the RLS migration — left untouched because it's the revision ID already stamped as applied against the real Supabase database per the 2026-07-08 migration history; renaming it would desync prod's `alembic_version` table). Task 3's new migration builds on this head.

- [ ] **Step 1: Confirm the collision and the correct fix target**

Run: `cd backend && python -m alembic heads`
Expected: fails with `alembic.script.revision.CycleDetected: Cycle is detected in revisions (...)` listing many revision IDs including `a1b2c3d4e5f6` twice implicitly (both files declare it).

- [ ] **Step 2: Create the renamed file with the corrected revision ID**

Create `backend/alembic/versions/c9d1e2f3a4b5_create_action_recommendations_table.py` with this exact content (identical to the original file except the revision ID on line 3 and line 13):

```python
"""create_action_recommendations_table

Revision ID: c9d1e2f3a4b5
Revises: f8a9b0c1d2e3
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_recommendations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('geo_score_id', sa.UUID(), nullable=True),
        sa.Column('action_text', sa.Text(), nullable=False),
        sa.Column('dimension', sa.String(length=40), nullable=False),
        sa.Column('estimated_impact', sa.Float(), nullable=False, server_default='0'),
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['geo_score_id'], ['geo_scores.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_action_recommendations_client_id', 'action_recommendations', ['client_id']
    )


def downgrade() -> None:
    op.drop_index('ix_action_recommendations_client_id', table_name='action_recommendations')
    op.drop_table('action_recommendations')
```

Then delete the old file:

Run: `git rm backend/alembic/versions/a1b2c3d4e5f6_create_action_recommendations_table.py`
Expected: file removed from the working tree and staged for deletion.

- [ ] **Step 3: Fix the downstream migration's `down_revision`**

In `backend/alembic/versions/b2c3d4e5f6a7_add_manual_score_evidence_to_clients.py`, change line 14 from:

```python
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
```

to:

```python
down_revision: Union[str, None] = 'c9d1e2f3a4b5'
```

- [ ] **Step 4: Verify the chain is now a single unambiguous line**

Run: `cd backend && python -m alembic heads`
Expected: prints exactly one head, `a1b2c3d4e5f6` (the RLS-enable migration — now correctly reachable through a clean, non-colliding chain).

Run: `cd backend && python -m alembic history | head -5`
Expected: no error, shows the chain terminating at `a1b2c3d4e5f6 (head)`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/c9d1e2f3a4b5_create_action_recommendations_table.py backend/alembic/versions/b2c3d4e5f6a7_add_manual_score_evidence_to_clients.py
git commit -m "fix(alembic): resolve duplicate revision ID collision (a1b2c3d4e5f6)

Two unrelated migrations both used revision a1b2c3d4e5f6, making alembic
heads raise CycleDetected with no valid single head. Renamed the older
(2026-06-10) create_action_recommendations_table migration to a fresh ID;
left the newer RLS-enable migration's ID untouched since it's already
stamped as applied against the real Supabase alembic_version table."
```

---

### Task 2: `ShareOfSourceSnapshot` model

**Files:**
- Create: `backend/app/models/share_of_source_snapshot.py`
- Modify: `backend/tests/conftest.py:8` (add the new model to the import list so `Base.metadata.create_all` picks up the table in tests)

**Interfaces:**
- Produces: `ShareOfSourceSnapshot` — columns `id`, `client_id`, `scan_id` (unique), `computed_at`, `total_third_party_sources: int`, `client_share_pct: float`, `competitor_shares: list` (JSON), `acquisition_list: list` (JSON). Used by Task 3 (migration), Task 5 (persistence), Task 6 (flip detection), Task 8 (history read).

- [ ] **Step 1: Create the model**

```python
# backend/app/models/share_of_source_snapshot.py
import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShareOfSourceSnapshot(Base):
    """One persisted Share-of-Source computation per completed scan.

    Written by provenance_service.compute_and_persist_snapshot right after
    enrich_scan_sources in scan_service's post-commit flow (best-effort,
    never blocks the scan). Enables a trend read (history endpoint) and
    flip detection that compute_share_of_source's live, recompute-on-read
    behavior can't provide alone. See
    docs/superpowers/specs/2026-07-10-share-of-source-trend-flip-detection-design.md.
    """

    __tablename__ = "share_of_source_snapshots"
    __table_args__ = (
        UniqueConstraint("scan_id", name="uq_share_of_source_snapshots_scan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_third_party_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    client_share_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    competitor_shares: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    acquisition_list: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
```

- [ ] **Step 2: Register the model in the test bootstrap**

In `backend/tests/conftest.py`, change line 8 from:

```python
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log  # noqa: F401
```

to:

```python
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot  # noqa: F401
```

- [ ] **Step 3: Verify the table is created in the test DB**

Run:
```bash
cd backend && python -c "
from sqlalchemy import create_engine, inspect
from app.models.base import Base
from app.models import client, competitor, scan, scan_query_result, scan_query_source, geo_score, activity_log, toolkit_files, report, content_brief, content_analysis, content_roadmap, ai_traffic_snapshot, action_recommendation, remediation_item, dimension_assessment, llm_call_log, share_of_source_snapshot
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
print('share_of_source_snapshots' in inspect(engine).get_table_names())
"
```
Expected: prints `True`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/share_of_source_snapshot.py backend/tests/conftest.py
git commit -m "feat(provenance): add ShareOfSourceSnapshot model"
```

---

### Task 3: Alembic migration for `share_of_source_snapshots`

**Files:**
- Create: `backend/alembic/versions/e8f9a0b1c2d3_create_share_of_source_snapshots_table.py`

**Interfaces:**
- Consumes: Task 1's fixed head `a1b2c3d4e5f6`.
- Produces: the `share_of_source_snapshots` table in Postgres, RLS enabled in the same migration (matching the `a1b2c3d4e5f6_enable_rls_scan_query_sources.py` precedent — RLS is never left as a follow-up step for a new table in this codebase going forward).

- [ ] **Step 1: Write the migration**

```python
# backend/alembic/versions/e8f9a0b1c2d3_create_share_of_source_snapshots_table.py
"""create share_of_source_snapshots table

Revision ID: e8f9a0b1c2d3
Revises: a1b2c3d4e5f6
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_of_source_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("total_third_party_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_share_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("competitor_shares", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("acquisition_list", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", name="uq_share_of_source_snapshots_scan_id"),
    )
    op.create_index(
        "ix_share_of_source_snapshots_client_id", "share_of_source_snapshots", ["client_id"]
    )
    op.execute("ALTER TABLE share_of_source_snapshots ENABLE ROW LEVEL SECURITY;")


def downgrade() -> None:
    op.execute("ALTER TABLE share_of_source_snapshots DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_share_of_source_snapshots_client_id", table_name="share_of_source_snapshots")
    op.drop_table("share_of_source_snapshots")
```

- [ ] **Step 2: Verify the migration chain is valid**

Run: `cd backend && python -m alembic heads`
Expected: prints exactly one head, `e8f9a0b1c2d3`.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/e8f9a0b1c2d3_create_share_of_source_snapshots_table.py
git commit -m "feat(provenance): migration for share_of_source_snapshots table (RLS on)"
```

**Note for later (out of scope here, flag don't fix):** this migration has only been validated against SQLite (tests) and `alembic heads`/`history` locally — per the existing handoff note, running it against the real Supabase Postgres is a separate, required step before this feature is considered prod-verified (same caveat that already applies to the provenance feature it extends).

---

### Task 4: Refactor `provenance_service` into `_collect_sources` + `_summarize`

**Files:**
- Modify: `backend/app/services/provenance_service.py:184-285` (the body of `compute_share_of_source`)
- Test: `backend/tests/test_provenance_share.py` (no new tests in this task — existing tests are the safety net for behavior preservation)

**Interfaces:**
- Produces:
  - `_collect_sources(scan_id: uuid.UUID, db: Session) -> dict[str, dict]` — keys are source URLs; each value is `{"domain": str, "title": str | None, "present": {"client": bool, "competitors": list[str]}, "count": int}`.
  - `_summarize(unique: dict[str, dict], competitors: list[Competitor], client: Client | None, last_scan_at: str | None) -> ShareOfSourceResponse`
  - `compute_share_of_source(client_id, db) -> ShareOfSourceResponse` — same signature and behavior as today, now implemented in terms of the two helpers above.
- Consumed by: Task 5 (`compute_and_persist_snapshot` calls both helpers directly).

- [ ] **Step 1: Run the existing tests first to establish the safety net**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -v`
Expected: all existing tests PASS (this is the baseline the refactor must not break — no new failing test is written for a pure refactor; the existing suite is the spec).

- [ ] **Step 2: Replace `compute_share_of_source`'s body with the two extracted helpers**

In `backend/app/services/provenance_service.py`, replace lines 184-285 (the entire current `compute_share_of_source` function, from `def compute_share_of_source` to the final `return ShareOfSourceResponse(...)`) with:

```python
def _collect_sources(scan_id: uuid.UUID, db: Session) -> dict[str, dict]:
    """Unique third-party sources cited by a scan's client-owned queries.

    Keyed by URL; kept in memory by callers that need raw per-URL presence
    data (flip detection), not just the summarized acquisition list that
    _summarize derives from it.
    """
    rows = (
        db.query(ScanQuerySource)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQuerySource.source_type == "third_party",
            ScanQuerySource.fetch_status == "ok",
        )
        .all()
    )
    unique: dict[str, dict] = {}
    for row in rows:
        if row.url not in unique:
            unique[row.url] = {
                "domain": row.domain,
                "title": row.title,
                "present": row.present_brands or {"client": False, "competitors": []},
                "count": 0,
            }
        unique[row.url]["count"] += 1
    return unique


def _summarize(
    unique: dict[str, dict],
    competitors: list[Competitor],
    client: Client | None,
    last_scan_at: str | None,
) -> ShareOfSourceResponse:
    """Pure math over a _collect_sources() result: shares + acquisition list."""
    denom = len(unique)
    if denom == 0:
        return _empty_share(last_scan_at)

    comp_names = {str(c.id): c.name for c in competitors}

    client_present = sum(1 for u in unique.values() if u["present"].get("client"))
    comp_present_counts: dict[str, int] = {cid: 0 for cid in comp_names}
    for u in unique.values():
        for cid in u["present"].get("competitors", []):
            if cid in comp_present_counts:
                comp_present_counts[cid] += 1

    def pct(n: int) -> float:
        return round(n / denom * 100, 1) if denom else 0.0

    client_share = BrandShare(
        competitor_id=None,
        name=client.name if client else "You",
        sources_present=client_present,
        share_pct=pct(client_present),
    )
    competitor_shares = [
        BrandShare(
            competitor_id=uuid.UUID(cid),
            name=comp_names[cid],
            sources_present=n,
            share_pct=pct(n),
        )
        for cid, n in sorted(comp_present_counts.items(), key=lambda kv: -kv[1])
    ]

    acquisition = []
    for url, meta in unique.items():
        present = meta["present"]
        comp_ids = [cid for cid in present.get("competitors", []) if cid in comp_names]
        if not present.get("client") and comp_ids:
            acquisition.append(
                AcquisitionSource(
                    url=url,
                    domain=meta["domain"],
                    title=meta["title"],
                    citation_count=meta["count"],
                    competitors_present=[
                        SourcePresence(competitor_id=uuid.UUID(cid), name=comp_names[cid])
                        for cid in comp_ids
                    ],
                )
            )
    acquisition.sort(key=lambda a: -a.citation_count)

    return ShareOfSourceResponse(
        last_scan_at=last_scan_at,
        total_third_party_sources=denom,
        client_share=client_share,
        competitor_shares=competitor_shares,
        acquisition_list=acquisition,
        flip_targets=acquisition[:3],
    )


def compute_share_of_source(client_id: uuid.UUID, db: Session) -> ShareOfSourceResponse:
    """Admin read model: Share-of-Source + acquisition list from the latest scan.

    Denominator is the count of unique third-party source URLs (fetch_status ok)
    cited by the client's own queries. A URL cited N times counts once for share
    but its N citations drive acquisition-list ranking.
    """
    latest = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )
    if not latest:
        return _empty_share(None)
    last_scan_at = latest.completed_at.isoformat() + "Z" if latest.completed_at else None

    unique = _collect_sources(latest.id, db)
    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()
    client = db.get(Client, client_id)
    return _summarize(unique, competitors, client, last_scan_at)
```

- [ ] **Step 3: Run the existing tests again to confirm behavior is preserved**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -v`
Expected: all tests PASS, identically to Step 1 (same pass count, same test names) — this proves the refactor didn't change `compute_share_of_source`'s behavior.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/provenance_service.py
git commit -m "refactor(provenance): extract _collect_sources + _summarize helpers

Behavior-preserving split of compute_share_of_source so the upcoming
snapshot-persistence path can reuse the same query + math without
duplicating it. Existing test_provenance_share.py passes unchanged."
```

---

### Task 5: `compute_and_persist_snapshot` (persistence only, no flip detection yet)

**Files:**
- Modify: `backend/app/services/provenance_service.py` (add import + new function)
- Test: `backend/tests/test_provenance_share.py` (add tests)

**Interfaces:**
- Consumes: `_collect_sources`, `_summarize` (Task 4), `ShareOfSourceSnapshot` (Task 2).
- Produces: `compute_and_persist_snapshot(scan_id: uuid.UUID, client_id: uuid.UUID, db: Session) -> ShareOfSourceSnapshot | None`. Returns `None` when there's nothing to persist (no third-party sources yet) or when persistence itself fails (logged, not raised). Consumed by Task 6 (flip detection, added inside this same function) and Task 7 (the scan_service hook).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_provenance_share.py`:

```python
def test_persist_snapshot_matches_live_compute(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    live = ps.compute_share_of_source(client.id, db)
    snapshot = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert snapshot is not None
    assert snapshot.scan_id == scan.id
    assert snapshot.client_id == client.id
    assert snapshot.total_third_party_sources == live.total_third_party_sources
    assert snapshot.client_share_pct == live.client_share.share_pct
    assert len(snapshot.acquisition_list) == len(live.acquisition_list)
    assert snapshot.acquisition_list[0]["domain"] == live.acquisition_list[0].domain
    assert snapshot.acquisition_list[0]["citation_count"] == live.acquisition_list[0].citation_count


def test_persist_snapshot_no_third_party_sources_returns_none(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    from datetime import datetime
    scan = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
    db.add(scan)
    db.commit()

    result = ps.compute_and_persist_snapshot(scan.id, client.id, db)
    assert result is None
    assert db.query(ps.ShareOfSourceSnapshot).count() == 0


def test_persist_snapshot_swallows_internal_failure(db, monkeypatch):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    monkeypatch.setattr(ps, "_summarize", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    result = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert result is None
    assert db.query(ps.ShareOfSourceSnapshot).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -k persist_snapshot -v`
Expected: FAIL — `AttributeError: module 'app.services.provenance_service' has no attribute 'compute_and_persist_snapshot'`

- [ ] **Step 3: Add the import and the new function**

In `backend/app/services/provenance_service.py`, add to the imports (near the other model imports at the top):

```python
from app.models.share_of_source_snapshot import ShareOfSourceSnapshot
```

Then append this function at the end of the file (flip detection is added to it in Task 6 — for this task it's persistence-only):

```python
def compute_and_persist_snapshot(
    scan_id: uuid.UUID, client_id: uuid.UUID, db: Session
) -> ShareOfSourceSnapshot | None:
    """Persist a Share-of-Source snapshot for a just-completed scan.

    Called from scan_service.run_scan's post-commit best-effort block,
    immediately after enrich_scan_sources. Best-effort by design: this
    function catches its own persistence failures so a bug here can never
    undo the scan that was already committed — the caller wraps this call
    in its own try/except too, matching every other post-commit step, as a
    defense-in-depth backstop.

    Returns None when there's nothing to persist yet (no third-party
    sources for this scan) or when persistence itself fails.
    """
    try:
        unique = _collect_sources(scan_id, db)
        if not unique:
            return None

        competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()
        client = db.get(Client, client_id)
        summary = _summarize(unique, competitors, client, last_scan_at=None)

        snapshot = ShareOfSourceSnapshot(
            client_id=client_id,
            scan_id=scan_id,
            total_third_party_sources=summary.total_third_party_sources,
            client_share_pct=summary.client_share.share_pct if summary.client_share else 0.0,
            competitor_shares=[cs.model_dump(mode="json") for cs in summary.competitor_shares],
            acquisition_list=[a.model_dump(mode="json") for a in summary.acquisition_list],
        )
        db.add(snapshot)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "share_of_source_snapshot_persist_failed", scan_id=str(scan_id), error=str(exc)
        )
        return None

    return snapshot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -k persist_snapshot -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provenance_service.py backend/tests/test_provenance_share.py
git commit -m "feat(provenance): persist Share-of-Source snapshot per scan"
```

---

### Task 6: Flip detection

**Files:**
- Modify: `backend/app/services/provenance_service.py` (add `_detect_flips`, wire into `compute_and_persist_snapshot`)
- Modify: `backend/tests/conftest.py` — no change needed (activity_log already imported)
- Test: `backend/tests/test_provenance_share.py`

**Interfaces:**
- Consumes: `unique` dict from `_collect_sources` (already computed in `compute_and_persist_snapshot`), `ShareOfSourceSnapshot` rows.
- Produces: `_detect_flips(client_id: uuid.UUID, new_scan_id: uuid.UUID, new_unique: dict[str, dict], db: Session) -> None` — writes `ActivityLog(event_type="citation_flip", ...)` rows. Called from inside `compute_and_persist_snapshot`, wrapped in its own try/except, after the snapshot commit.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_provenance_share.py`:

```python
def _seed_second_scan_client_now_present(db, client, comp):
    """Same client/comp as _seed_enriched, but a NEW scan where the client is
    now present at the g2.com URL that was previously an acquisition target."""
    from datetime import datetime
    scan2 = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
    db.add(scan2)
    sqr2 = ScanQueryResult(scan_id=scan2.id, platform="perplexity", category="recommendation",
                           query_text="best crm", response_text="…", brand_detected=True)
    sqr2.sources.append(ScanQuerySource(
        url="https://g2.com/crm", domain="g2.com", title="G2 CRMs", rank=1,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": [str(comp.id)]}))
    db.add(sqr2)
    db.commit()
    return scan2


def test_flip_detected_when_client_now_present(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan1 = db.query(Scan).filter(Scan.client_id == client.id).first()
    ps.compute_and_persist_snapshot(scan1.id, client.id, db)  # first snapshot: g2.com is an acquisition target

    scan2 = _seed_second_scan_client_now_present(db, client, comp)
    ps.compute_and_persist_snapshot(scan2.id, client.id, db)

    flips = db.query(ActivityLog).filter(
        ActivityLog.client_id == client.id, ActivityLog.event_type == "citation_flip"
    ).all()
    assert len(flips) == 1
    assert "g2.com" in flips[0].note
    assert client.name in flips[0].note


def test_no_flip_when_url_absent_from_new_scan(db):
    """A URL from the previous snapshot's acquisition list that simply doesn't
    reappear in the new scan is search-result drift, not a verified flip."""
    from app.services import provenance_service as ps
    from datetime import datetime
    client, comp = _seed_enriched(db)
    scan1 = db.query(Scan).filter(Scan.client_id == client.id).first()
    ps.compute_and_persist_snapshot(scan1.id, client.id, db)

    # New scan with a completely different, unrelated third-party source —
    # g2.com never shows up at all.
    scan2 = Scan(id=uuid.uuid4(), client_id=client.id, status="completed", completed_at=datetime.utcnow())
    db.add(scan2)
    sqr2 = ScanQueryResult(scan_id=scan2.id, platform="perplexity", category="recommendation",
                           query_text="best crm", response_text="…", brand_detected=False)
    sqr2.sources.append(ScanQuerySource(
        url="https://capterra.com/x", domain="capterra.com", title="Capterra", rank=1,
        source_type="third_party", fetch_status="ok",
        present_brands={"client": True, "competitors": []}))
    db.add(sqr2)
    db.commit()
    ps.compute_and_persist_snapshot(scan2.id, client.id, db)

    flips = db.query(ActivityLog).filter(ActivityLog.event_type == "citation_flip").all()
    assert len(flips) == 0


def test_first_scan_no_previous_snapshot_no_flip_no_error(db):
    from app.services import provenance_service as ps
    client, comp = _seed_enriched(db)
    scan = db.query(Scan).filter(Scan.client_id == client.id).first()

    snapshot = ps.compute_and_persist_snapshot(scan.id, client.id, db)

    assert snapshot is not None
    flips = db.query(ActivityLog).filter(ActivityLog.event_type == "citation_flip").all()
    assert len(flips) == 0
```

Add this import at the top of `backend/tests/test_provenance_share.py` (alongside the existing model imports):

```python
from app.models.activity_log import ActivityLog
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -k flip -v`
Expected: FAIL — `test_flip_detected_when_client_now_present` and friends fail with `assert 0 == 1` or similar (no flip-detection logic exists yet).

- [ ] **Step 3: Add `_detect_flips` and wire it into `compute_and_persist_snapshot`**

In `backend/app/services/provenance_service.py`, add the import:

```python
from app.models.activity_log import ActivityLog
```

Add this new function (place it right before `compute_and_persist_snapshot`):

```python
def _detect_flips(
    client_id: uuid.UUID, new_scan_id: uuid.UUID, new_unique: dict[str, dict], db: Session
) -> None:
    """Compare the client's previous snapshot's acquisition_list against the
    freshly-collected new_unique data; log a verified citation_flip for every
    URL that went from (client absent, competitor present) to (client
    present) between the two snapshots.

    Skips URLs that don't reappear in new_unique at all — that's
    search-result drift, not a verified flip. Runs after the new snapshot is
    already committed; the caller wraps this in its own try/except so a bug
    here can only cost this run's activity-log entries, never the snapshot.
    """
    previous = (
        db.query(ShareOfSourceSnapshot)
        .filter(
            ShareOfSourceSnapshot.client_id == client_id,
            ShareOfSourceSnapshot.scan_id != new_scan_id,
        )
        .order_by(ShareOfSourceSnapshot.computed_at.desc())
        .first()
    )
    if previous is None:
        return

    client = db.get(Client, client_id)
    client_name = client.name if client else "your business"

    for entry in previous.acquisition_list:
        url = entry.get("url")
        new_entry = new_unique.get(url)
        if new_entry is None:
            continue  # not verified — the URL didn't reappear this scan
        if new_entry["present"].get("client"):
            competitor_names = ", ".join(
                c.get("name", "") for c in entry.get("competitors_present", [])
            )
            note = f"{new_entry['domain']} now cites {client_name}"
            if competitor_names:
                note += f" — previously only cited {competitor_names}"
            db.add(ActivityLog(client_id=client_id, event_type="citation_flip", note=note))
    db.commit()
```

Then update `compute_and_persist_snapshot` to call it after the snapshot commit — replace the final `return snapshot` line with:

```python
    try:
        _detect_flips(client_id, scan_id, unique, db)
    except Exception as exc:
        db.rollback()
        logger.error("citation_flip_detection_failed", scan_id=str(scan_id), error=str(exc))

    return snapshot
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -v`
Expected: PASS — all tests in the file, including the original ones from before this feature (full regression check).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provenance_service.py backend/tests/test_provenance_share.py
git commit -m "feat(provenance): verified citation-flip detection

Logs an ActivityLog(event_type='citation_flip') when a source that
previously cited only a competitor now also cites the client. Only
counts verified reappearances of the same URL in the new scan — a URL
that simply drops out of results is treated as search drift, not a flip."
```

---

### Task 7: Hook into `scan_service.run_scan`'s post-commit flow

**Files:**
- Modify: `backend/app/services/scan_service.py:344-349`
- Test: `backend/tests/test_scan_service.py`

**Interfaces:**
- Consumes: `provenance_service.compute_and_persist_snapshot` (Task 5+6).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_scan_service.py`, right after `test_run_scan_rolls_back_when_post_commit_alert_raises` (mirrors it exactly):

```python
def test_run_scan_rolls_back_when_post_commit_snapshot_raises():
    """A swallowed Share-of-Source snapshot exception must not leave
    uncommitted state on the session — run_scan rolls back after catching it,
    and the scan itself still completes."""
    scan = make_scan()
    client = make_client()
    mock_db = setup_db(scan, client, [make_result()])

    patcher, _ = patch_platform_client(lambda q: "ACME Corp great.")
    with patcher, patch("app.services.scan_service.time.sleep"), patch(
        "app.services.scan_service.extract_position", return_value=None
    ), patch(
        "app.services.provenance_service.compute_and_persist_snapshot",
        side_effect=Exception("snapshot boom"),
    ):
        run_scan(scan.id, mock_db)

    assert scan.status == "completed"
    assert mock_db.rollback.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_scan_service.py -k snapshot_raises -v`
Expected: FAIL — the patch target `app.services.provenance_service.compute_and_persist_snapshot` doesn't get called at all yet (scan_service doesn't call it), so `scan.status == "completed"` passes trivially but this is establishing the call site; more precisely it will currently just pass without exercising the new code path — proceed to Step 3 regardless, then re-run in Step 4 to confirm the hook is live (the meaningful assertion is that adding the hook doesn't regress `test_run_scan_sets_status_to_completed`, checked in Step 4).

- [ ] **Step 3: Add the hook point**

In `backend/app/services/scan_service.py`, immediately after the existing `enrich_scan_sources` block (lines 341-349) and before the outer `except Exception as exc:` (line 351), add:

```python
        # Share-of-Source snapshot + flip detection — persists a trend point
        # for this scan and logs a citation_flip ActivityLog when a source
        # that used to cite only a competitor now cites the client too.
        # Best-effort: on failure roll back and swallow so a bug here never
        # undoes a good scan (CLAUDE.md §10). The function also has its own
        # internal isolation between persistence and flip detection; this
        # try/except is a defense-in-depth backstop matching every other
        # post-commit step in this function.
        try:
            from app.services.provenance_service import compute_and_persist_snapshot
            compute_and_persist_snapshot(scan.id, client.id, db)
        except Exception as exc:
            db.rollback()
            logger.error(
                "share_of_source_snapshot_failed", scan_id=str(scan_id), error=str(exc)
            )
```

- [ ] **Step 4: Run tests to verify everything passes, including the full existing suite**

Run: `cd backend && python -m pytest tests/test_scan_service.py -v`
Expected: PASS — all tests, including the new `test_run_scan_rolls_back_when_post_commit_snapshot_raises` and every pre-existing test (`test_run_scan_sets_status_to_completed`, `test_run_scan_creates_geo_score_with_platform_breakdown`, etc.) unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scan_service.py backend/tests/test_scan_service.py
git commit -m "feat(scan): persist Share-of-Source snapshot after every scan

Hooked into run_scan's existing post-commit best-effort block, right
after enrich_scan_sources (snapshot data needs enrichment's present_brands
to already be populated). Isolated like every other post-commit step —
a failure here never undoes the scan."
```

---

### Task 8: History read API

**Files:**
- Modify: `backend/app/schemas/provenance.py` (add `ShareOfSourceHistoryPoint`)
- Modify: `backend/app/services/provenance_service.py` (add `get_share_of_source_history`)
- Modify: `backend/app/api/v1/competitors.py` (add the route)
- Test: `backend/tests/test_provenance_share.py`, `backend/tests/test_api_provenance.py`

**Interfaces:**
- Produces: `GET /api/v1/clients/{client_id}/competitors/provenance/history` → `list[ShareOfSourceHistoryPoint]`, oldest→newest, capped at 12. (See deviation #2 above for why this path, not `/share-of-source/history`.)
- Produces: `get_share_of_source_history(client_id: uuid.UUID, db: Session, limit: int = 12) -> list[ShareOfSourceHistoryPoint]`.

- [ ] **Step 1: Write the failing service-level test**

Add to `backend/tests/test_provenance_share.py`:

```python
def test_history_returns_oldest_to_newest_capped_at_limit(db):
    from app.services import provenance_service as ps
    from datetime import datetime, timedelta
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()

    base = datetime(2026, 1, 1)
    for i in range(15):
        snap = ps.ShareOfSourceSnapshot(
            client_id=client.id, scan_id=uuid.uuid4(),
            computed_at=base + timedelta(days=i),
            total_third_party_sources=i, client_share_pct=float(i),
        )
        db.add(snap)
    db.commit()

    history = ps.get_share_of_source_history(client.id, db)
    assert len(history) == 12
    assert history[0].client_share_pct < history[-1].client_share_pct  # oldest first
    assert history[-1].client_share_pct == 14.0  # newest of the 15 seeded


def test_history_empty_for_client_with_no_snapshots(db):
    from app.services import provenance_service as ps
    client = Client(id=uuid.uuid4(), name="Acme", website="https://acme.com", industry="dentist")
    db.add(client)
    db.commit()
    assert ps.get_share_of_source_history(client.id, db) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -k history -v`
Expected: FAIL — `AttributeError: module 'app.services.provenance_service' has no attribute 'get_share_of_source_history'`

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/provenance.py`, append:

```python
class ShareOfSourceHistoryPoint(BaseModel):
    computed_at: str
    client_share_pct: float
    total_third_party_sources: int
```

- [ ] **Step 4: Add the service function**

In `backend/app/services/provenance_service.py`, add to the imports:

```python
from app.schemas.provenance import (
    AcquisitionSource,
    BrandShare,
    ShareOfSourceHistoryPoint,
    ShareOfSourceResponse,
    SourcePresence,
)
```

(This replaces the existing import block for `app.schemas.provenance` — same names plus `ShareOfSourceHistoryPoint`.)

Add this function at the end of the file:

```python
def get_share_of_source_history(
    client_id: uuid.UUID, db: Session, limit: int = 12
) -> list[ShareOfSourceHistoryPoint]:
    """Last `limit` Share-of-Source snapshots for a client, oldest → newest."""
    rows = (
        db.query(ShareOfSourceSnapshot)
        .filter(ShareOfSourceSnapshot.client_id == client_id)
        .order_by(ShareOfSourceSnapshot.computed_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [
        ShareOfSourceHistoryPoint(
            computed_at=r.computed_at.isoformat() + "Z",
            client_share_pct=r.client_share_pct,
            total_third_party_sources=r.total_third_party_sources,
        )
        for r in rows
    ]
```

- [ ] **Step 5: Run the service-level tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_provenance_share.py -v`
Expected: PASS — full file, including everything from Tasks 4-6.

- [ ] **Step 6: Write the failing API test**

Add to `backend/tests/test_api_provenance.py`:

```python
def test_history_returns_points(monkeypatch):
    from app.schemas.provenance import ShareOfSourceHistoryPoint
    app, get_db = _make_app()
    client_id = uuid.uuid4()
    mock_db = MagicMock()
    mock_db.get.return_value = _fake_client(client_id)
    app.dependency_overrides[get_db] = lambda: mock_db

    points = [ShareOfSourceHistoryPoint(
        computed_at="2026-07-01T00:00:00Z", client_share_pct=25.0, total_third_party_sources=4
    )]
    import app.api.v1.competitors as comp_api
    monkeypatch.setattr(comp_api, "get_share_of_source_history", lambda cid, db: points)

    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{client_id}/competitors/provenance/history")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == [{"computed_at": "2026-07-01T00:00:00Z", "client_share_pct": 25.0, "total_third_party_sources": 4}]


def test_history_client_not_found_404():
    app, get_db = _make_app()
    mock_db = MagicMock()
    mock_db.get.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db
    http = TestClient(app)
    resp = http.get(f"/api/v1/clients/{uuid.uuid4()}/competitors/provenance/history")
    app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_provenance.py -k history -v`
Expected: FAIL — 404 route not found (no such endpoint exists yet).

- [ ] **Step 8: Add the route**

In `backend/app/api/v1/competitors.py`, update the import on line 20 from:

```python
from app.schemas.provenance import ShareOfSourceResponse
```

to:

```python
from app.schemas.provenance import ShareOfSourceHistoryPoint, ShareOfSourceResponse
```

Update the import on line 27 from:

```python
from app.services.provenance_service import compute_share_of_source
```

to:

```python
from app.services.provenance_service import compute_share_of_source, get_share_of_source_history
```

Add this route immediately after `get_provenance` (after line 70, before the `@router.post("/win-loss/{result_id}/brief"...` block):

```python
@router.get(
    "/provenance/history",
    response_model=list[ShareOfSourceHistoryPoint],
    dependencies=[Depends(require_api_key)],
)
def get_provenance_history(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return get_share_of_source_history(client_id, db)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_provenance.py -v`
Expected: PASS — all 4 tests in the file (2 existing + 2 new).

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/provenance.py backend/app/services/provenance_service.py backend/app/api/v1/competitors.py backend/tests/test_provenance_share.py backend/tests/test_api_provenance.py
git commit -m "feat(provenance): Share-of-Source trend history endpoint

GET /clients/{id}/competitors/provenance/history returns the last 12
snapshots, oldest to newest. Existing /provenance endpoint is untouched."
```

---

### Task 9: Frontend — trend sparkline on the competitors page

**Files:**
- Modify: `frontend/src/types/index.ts` (add `ShareOfSourceHistoryPoint`)
- Modify: `frontend/src/lib/api.ts` (add `getShareOfSourceHistory`)
- Create: `frontend/src/components/competitors/ShareOfSourceSparkline.tsx`
- Modify: `frontend/src/components/competitors/ShareOfSourceSection.tsx`
- Modify: `frontend/src/app/clients/[id]/competitors/page.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/clients/{id}/competitors/provenance/history` (Task 8).
- Produces: `<ShareOfSourceSparkline points={history} />` rendered inside the existing Share-of-Source card.

- [ ] **Step 1: Add the type**

In `frontend/src/types/index.ts`, append after the `ShareOfSource` interface (after line 652):

```typescript
export interface ShareOfSourceHistoryPoint {
  computed_at: string
  client_share_pct: number
  total_third_party_sources: number
}
```

- [ ] **Step 2: Add the API function**

In `frontend/src/lib/api.ts`, add `ShareOfSourceHistoryPoint` to the type import on line 4 (append it to the existing destructured import list ending in `ShareOfSource`):

```typescript
import type { Client, ClientListItem, Competitor, GeoScore, ToolkitFiles, VerificationResult, CompetitorIntelligenceResponse, ActivityLogEntry, Report, Scan, ContentAnalysis, ContentRoadmap, ActionRecommendation, AiTrafficSnapshot, ShareTokenResponse, WinLossResponse, ContentBrief, CompetitorTrendsResponse, IndustryBenchmark, ScanDiffResponse, GapMatrixResponse, RemediationItem, RemediationStatus, DimensionAssessment, AssessmentDimension, ShareOfSource, ShareOfSourceHistoryPoint } from "@/types"
```

Add this function right after `getProvenance` (after line 216):

```typescript
export function getShareOfSourceHistory(clientId: string): Promise<ShareOfSourceHistoryPoint[]> {
  return apiFetch<ShareOfSourceHistoryPoint[]>(`/api/v1/clients/${clientId}/competitors/provenance/history`)
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (existing baseline unaffected).

- [ ] **Step 3: Create the sparkline component**

```tsx
// frontend/src/components/competitors/ShareOfSourceSparkline.tsx
import type { ShareOfSourceHistoryPoint } from "@/types"

const WIDTH = 240
const HEIGHT = 48
const PAD = 4

export function ShareOfSourceSparkline({ points }: { points: ShareOfSourceHistoryPoint[] }) {
  if (points.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        Trend appears after your next scan — need at least two data points.
      </p>
    )
  }

  const values = points.map((p) => p.client_share_pct)
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const stepX = (WIDTH - PAD * 2) / (points.length - 1)

  const coords = values.map((v, i) => {
    const x = PAD + i * stepX
    const y = PAD + (1 - (v - min) / range) * (HEIGHT - PAD * 2)
    return `${x},${y}`
  })

  const first = values[0]
  const last = values[values.length - 1]
  const delta = last - first
  const trendLabel =
    delta > 0.5 ? `+${delta.toFixed(1)}pt` : delta < -0.5 ? `${delta.toFixed(1)}pt` : "flat"
  const trendColor = delta > 0.5 ? "text-score-good" : delta < -0.5 ? "text-score-critical" : "text-muted-foreground"

  return (
    <div className="flex items-center gap-3">
      <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="shrink-0">
        <polyline
          points={coords.join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="text-primary"
        />
      </svg>
      <div className="text-xs">
        <div className="font-medium tabular-nums">{last.toFixed(0)}% now</div>
        <div className={`tabular-nums ${trendColor}`}>{trendLabel} vs {points.length} scans ago</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Wire the sparkline into the existing Share-of-Source section**

In `frontend/src/components/competitors/ShareOfSourceSection.tsx`, update the imports (line 1-2) to:

```tsx
import { ExternalLink } from "lucide-react"
import type { ShareOfSource, ShareOfSourceHistoryPoint } from "@/types"
import { ShareOfSourceSparkline } from "./ShareOfSourceSparkline"
```

Change the component signature (line 4) from:

```tsx
export function ShareOfSourceSection({ data }: { data: ShareOfSource }) {
```

to:

```tsx
export function ShareOfSourceSection({
  data,
  history,
}: {
  data: ShareOfSource
  history: ShareOfSourceHistoryPoint[]
}) {
```

Add the sparkline right after the existing header paragraph inside the first card — insert this immediately after the `</p>` that closes line 31 (`category's questions, here is who shows up on them.` — the paragraph right before `<div className="mt-4 space-y-3">` at line 32):

```tsx
        {history.length >= 2 && (
          <div className="mt-3">
            <ShareOfSourceSparkline points={history} />
          </div>
        )}
```

- [ ] **Step 5: Wire the history fetch into the competitors page**

In `frontend/src/app/clients/[id]/competitors/page.tsx`, change line 4 from:

```tsx
import { getCompetitorIntelligence, getCompetitorTrends, getWinLoss, getProvenance } from "@/lib/api"
```

to:

```tsx
import { getCompetitorIntelligence, getCompetitorTrends, getWinLoss, getProvenance, getShareOfSourceHistory } from "@/lib/api"
```

Change lines 24-29 from:

```tsx
  const [data, winLoss, trends, provenance] = await Promise.all([
    getCompetitorIntelligence(id).catch(() => null),
    getWinLoss(id).catch(() => null),
    getCompetitorTrends(id).catch(() => null),
    getProvenance(id).catch(() => null),
  ])
```

to:

```tsx
  const [data, winLoss, trends, provenance, shareOfSourceHistory] = await Promise.all([
    getCompetitorIntelligence(id).catch(() => null),
    getWinLoss(id).catch(() => null),
    getCompetitorTrends(id).catch(() => null),
    getProvenance(id).catch(() => null),
    getShareOfSourceHistory(id).catch(() => []),
  ])
```

Change line 176 (the render line) from:

```tsx
      {provenance && <ShareOfSourceSection data={provenance} />}
```

to:

```tsx
      {provenance && <ShareOfSourceSection data={provenance} history={shareOfSourceHistory} />}
```

- [ ] **Step 6: Verify TypeScript compiles and the build succeeds**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Manual verification in the browser**

Start the dev server, open `/clients/[id]/competitors` for a client with ≥ 2 persisted snapshots (seed via two local test scans if none exist yet), confirm:
- The sparkline renders inside the existing Share-of-Source card.
- With < 2 snapshots, the "Trend appears after your next scan" message shows instead (no broken empty chart).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/components/competitors/ShareOfSourceSparkline.tsx frontend/src/components/competitors/ShareOfSourceSection.tsx "frontend/src/app/clients/[id]/competitors/page.tsx"
git commit -m "feat(competitors): Share-of-Source trend sparkline"
```

---

### Task 10: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the seenby-verify skill**

Invoke the `seenby-verify` skill. It runs backend tests, frontend typecheck/build, the banned-language grep, and migration sanity checks.

- [ ] **Step 2: Confirm the specific new/changed areas explicitly**

Run: `cd backend && python -m pytest tests/test_provenance_share.py tests/test_scan_service.py tests/test_api_provenance.py -v`
Expected: all PASS.

Run: `cd backend && python -m alembic heads`
Expected: exactly one head, `e8f9a0b1c2d3`.

- [ ] **Step 3: Report honestly**

State explicitly in the final report: this migration has only run against SQLite (tests) and been validated with `alembic heads`/`history` locally — it has **not** been run against the real Supabase Postgres. That's a required follow-up before this is prod-verified (same caveat already open for the underlying provenance feature per the 2026-07 handoff notes), not something this plan can close on its own.

---

## Self-Review

**Spec coverage:**
- §2 persistence trigger (on-demand, scan-driven) → Task 7. ✓
- §2 full acquisition list persisted → Task 5 (`acquisition_list` stores the full list, not a `[:3]` slice). ✓
- §2 flip surfacing (activity log only) → Task 6. ✓
- §2 flip accuracy (verified only, skip non-reappearing URLs) → Task 6, `_detect_flips`, the `continue` on `new_entry is None`, and `test_no_flip_when_url_absent_from_new_scan`. ✓
- §2 compute reuse (refactor, don't duplicate) → Task 4. ✓
- §2 no backfill → nothing in this plan generates historical snapshots; confirmed by omission. ✓
- §4 data model → Task 2 + 3. ✓
- §5 compute + write path, hook point → Task 7 (exact insertion point verified against the real file: after `enrich_scan_sources`, before the outer `except`). ✓
- §6 flip detection algorithm → Task 6. ✓
- §7 read API (live unchanged + new history endpoint) → Task 8 (path corrected to match the real shipped route — see deviation #2). ✓
- §8 frontend sparkline → Task 9. ✓
- §9 error handling (two isolated try/excepts, scan-flow isolation) → Task 5 (persist), Task 6 (flip), Task 7 (scan_service backstop). ✓
- §10 testing checklist items 1-6 → Tasks 5, 6, 8 cover all six explicitly (snapshot matches live compute, flip case, no-flip case, first-scan case, isolation case, history endpoint). ✓

**Placeholder scan:** no TBD/TODO, no "add appropriate error handling" hand-waves, no "similar to Task N" shorthand — every step has complete code. Confirmed clean on re-read.

**Type consistency:** `_collect_sources` returns `dict[str, dict]` consistently referenced in Tasks 4, 5, 6. `compute_and_persist_snapshot` returns `ShareOfSourceSnapshot | None` consistently in Tasks 5, 6, 7. `ShareOfSourceHistoryPoint` field names (`computed_at`, `client_share_pct`, `total_third_party_sources`) match exactly across the Pydantic schema (Task 8), the TS interface (Task 9), and every test. `get_share_of_source_history(client_id, db, limit=12)` signature matches its one call site in the new route.
