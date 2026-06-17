# Six Feature Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six independent admin-side enhancements to SeenBy — internal client notes, a scan-due reminder, a scan-to-scan diff, AI-response sentiment rating, a cross-client competitor gap matrix, and a shareable scan snippet image.

**Architecture:** Each feature is self-contained and can ship on its own. Backend follows the existing layering (models → schemas → services → `app/api/v1` routes; business logic never in routes). Three features add a column and therefore an Alembic migration. One feature (sentiment) adds an LLM call routed through the existing `prompts/registry.py` + `cost_tracker.py` infrastructure. The snippet feature uses Pillow (already a dependency) — **zero LLM calls**. Frontend calls go only through `src/lib/api.ts`; types live in `src/types/index.ts`.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, Anthropic SDK, Pillow, Next.js 15 (server components + server actions), shadcn/ui, pytest.

---

## Shared Conventions (read before any task)

- **Migrations:** Never hardcode a `down_revision`. Generate the scaffold with `alembic revision -m "<msg>"` from `backend/` so Alembic fills `down_revision` from the current head (a hardcoded id caused a duplicate-revision conflict on 2026-06-16). Then paste the `upgrade()`/`downgrade()` bodies from the task.
- **Language rules (CLAUDE.md §2):** Any text that can reach a client must use approved phrasing ("Seen by AI" / "Not seen by AI", "visibility frequency", "AI Search Ranking", "Your competitors are winning here"). Never "cited", "mentioned", "citation rate", "confidence", "token", "char offset".
- **Client-view guardrail (CLAUDE.md §9):** `internal_notes` and `sentiment` are admin-only. Do **not** add them to any schema in `app/schemas/client_view.py` or any `/view/[token]` surface.
- **Constants:** New tunables go in `app/core/constants.py` — no magic numbers in services.
- **Run backend tests from `backend/`:** `poetry run pytest <path> -v`.

---

## Feature 1: Internal Client Notes

Free-text admin notes per client (e.g. "prefers WhatsApp", "web dev is Ahmad 012-xxx"). Distinct from the system-generated activity log. Admin-only.

### Task 1.1: Add `internal_notes` column to the Client model

**Files:**
- Modify: `backend/app/models/client.py`
- Create: `backend/alembic/versions/<generated>_add_internal_notes_to_clients.py`

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/client.py`, after the `archived_at` column (line 44), add:

```python
    # Free-text admin notes (CRM-style). Admin-only — never exposed in client view.
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`Text` is already imported on line 3.

- [ ] **Step 2: Generate the migration scaffold**

Run from `backend/`:
```bash
poetry run alembic revision -m "add internal_notes to clients"
```
Expected: prints `Generating .../versions/<hash>_add_internal_notes_to_clients.py ... done`

- [ ] **Step 3: Fill in the migration body**

In the generated file, set:
```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("clients", sa.Column("internal_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "internal_notes")
```

- [ ] **Step 4: Apply the migration**

Run from `backend/`:
```bash
poetry run alembic upgrade head
```
Expected: `Running upgrade ... -> <hash>, add internal_notes to clients`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/client.py backend/alembic/versions/
git commit -m "feat(backend): add internal_notes column to clients"
```

### Task 1.2: Expose `internal_notes` in client schemas

**Files:**
- Modify: `backend/app/schemas/client.py`
- Test: `backend/tests/test_api_clients.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_clients.py` (mirror the existing client-create/update test style in that file — use the same `client` fixture and auth header helper already used there):

```python
def test_update_and_read_internal_notes(client, auth_headers):
    created = client.post(
        "/api/v1/clients",
        json={"name": "Note Co", "website": "https://noteco.example", "industry": "Dental"},
        headers=auth_headers,
    ).json()

    patched = client.patch(
        f"/api/v1/clients/{created['id']}",
        json={"internal_notes": "Prefers WhatsApp. Web dev: Ahmad 012-xxx."},
        headers=auth_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["internal_notes"] == "Prefers WhatsApp. Web dev: Ahmad 012-xxx."

    fetched = client.get(f"/api/v1/clients/{created['id']}", headers=auth_headers).json()
    assert fetched["internal_notes"] == "Prefers WhatsApp. Web dev: Ahmad 012-xxx."
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
poetry run pytest backend/tests/test_api_clients.py::test_update_and_read_internal_notes -v
```
Expected: FAIL — `internal_notes` not accepted/returned (KeyError or assertion on `None`).

- [ ] **Step 3: Add the field to the schemas**

In `backend/app/schemas/client.py`:

In `ClientUpdate` (after line 36, `is_prospect: bool | None = None`):
```python
    internal_notes: str | None = None
```

In `ClientResponse` (after line 77, `is_prospect: bool = False`):
```python
    internal_notes: str | None = None
```

(No change needed to the route — `update_client` already does `setattr` over `model_dump(exclude_unset=True)`.)

- [ ] **Step 4: Run the test to confirm it passes**

```bash
poetry run pytest backend/tests/test_api_clients.py::test_update_and_read_internal_notes -v
```
Expected: PASS

- [ ] **Step 5: Confirm client-view schemas are untouched**

```bash
grep -rn "internal_notes" backend/app/schemas/client_view.py backend/app/api/v1/client_view.py
```
Expected: no matches (guardrail holds).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client.py backend/tests/test_api_clients.py
git commit -m "feat(backend): expose internal_notes in client create/update/read"
```

### Task 1.3: Frontend — notes field on client settings

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts:48-76` (the `updateClient` body union)
- Modify: `frontend/src/app/clients/[id]/settings/page.tsx` (or the settings form component it renders)
- Create: `frontend/src/components/clients/InternalNotesCard.tsx`

- [ ] **Step 1: Add `internal_notes` to the `Client` type**

In `frontend/src/types/index.ts`, add `internal_notes: string | null` to the `Client` interface (alongside `is_prospect`).

- [ ] **Step 2: Allow `internal_notes` in `updateClient`**

In `frontend/src/lib/api.ts`, add `| "internal_notes"` to the `Pick<Client, ...>` union inside `updateClient` (line 48-76).

- [ ] **Step 3: Add a server action**

In `frontend/src/app/clients/[id]/settings/actions.ts` (create if absent, else the existing settings actions file), following the `updateClient`→`revalidatePath` pattern in `frontend/src/app/clients/actions.ts`:

```typescript
"use server"
import { updateClient as apiUpdateClient } from "@/lib/api"
import { revalidatePath } from "next/cache"

export async function saveInternalNotesAction(clientId: string, notes: string) {
  await apiUpdateClient(clientId, { internal_notes: notes })
  revalidatePath(`/clients/${clientId}/settings`)
}
```

- [ ] **Step 4: Build the notes card**

Create `frontend/src/components/clients/InternalNotesCard.tsx` — a client component with a shadcn `Textarea`, a "Save notes" `Button`, and a `sonner` toast on success (mirror the existing settings cards' card/header/footer markup). Label it clearly "Internal notes (admin only — never shown to the client)". Wire the button to `saveInternalNotesAction`.

- [ ] **Step 5: Render it on the settings page**

Import and render `InternalNotesCard` in the settings page, passing `client.id` and `client.internal_notes ?? ""`.

- [ ] **Step 6: Verify the frontend compiles**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/app/clients/[id]/settings frontend/src/components/clients/InternalNotesCard.tsx
git commit -m "feat(frontend): internal client notes on settings page"
```

---

## Feature 2: Scan Reminder ("next scan due")

Per-client review cadence; the all-clients page flags clients whose next scan is due/overdue. **No scheduler** — purely a computed date + badge (MVP excludes automated scans, CLAUDE.md §11).

### Task 2.1: Add `scan_cadence_days` column + constant

**Files:**
- Modify: `backend/app/core/constants.py`
- Modify: `backend/app/models/client.py`
- Create: `backend/alembic/versions/<generated>_add_scan_cadence_days_to_clients.py`

- [ ] **Step 1: Add the default constant**

In `backend/app/core/constants.py`, after `MAX_COMPETITORS` (line 81):
```python
# Default review cadence — drives the "next scan due" reminder on /clients.
# Reminder only; nothing auto-scans (MVP runs on-demand scans only).
DEFAULT_SCAN_CADENCE_DAYS: Final = 30
```

- [ ] **Step 2: Add the column to the model**

In `backend/app/models/client.py`, after the `internal_notes` column from Feature 1 (or after `archived_at` if Feature 1 not yet done):
```python
    # Admin review cadence in days; drives the "next scan due" reminder. Reminder only.
    scan_cadence_days: Mapped[int] = mapped_column(Integer, default=30, server_default=text("30"))
```
`Integer` and `text` are already imported (lines 3-4).

- [ ] **Step 3: Generate + fill the migration**

Run from `backend/`: `poetry run alembic revision -m "add scan_cadence_days to clients"`, then:
```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("scan_cadence_days", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_column("clients", "scan_cadence_days")
```

- [ ] **Step 4: Apply**

```bash
poetry run alembic upgrade head
```
Expected: upgrade runs cleanly.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/constants.py backend/app/models/client.py backend/alembic/versions/
git commit -m "feat(backend): add scan_cadence_days column for scan-due reminder"
```

### Task 2.2: Compute `next_scan_due` in the client list service

**Files:**
- Modify: `backend/app/schemas/client.py:87-94` (`ClientListItem`)
- Modify: `backend/app/services/client_list_service.py`
- Test: `backend/tests/test_client_list_service.py` (create)

- [ ] **Step 1: Add fields to `ClientListItem` + `scan_cadence_days` to `ClientUpdate`/`ClientResponse`**

In `backend/app/schemas/client.py`:
- `ClientUpdate`: add `scan_cadence_days: int | None = Field(default=None, ge=1, le=365)`
- `ClientResponse`: add `scan_cadence_days: int = 30`
- `ClientListItem` (after line 91): add
```python
    next_scan_due: datetime | None = None
    is_scan_overdue: bool = False
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_client_list_service.py`:
```python
from datetime import datetime, timedelta

from app.services.client_list_service import compute_next_scan_due


def test_next_scan_due_is_last_scan_plus_cadence():
    last = datetime(2026, 6, 1, 12, 0, 0)
    due = compute_next_scan_due(last_scan_at=last, cadence_days=30)
    assert due == datetime(2026, 7, 1, 12, 0, 0)


def test_next_scan_due_none_when_never_scanned():
    assert compute_next_scan_due(last_scan_at=None, cadence_days=30) is None


def test_overdue_when_due_date_in_past():
    last = datetime.utcnow() - timedelta(days=40)
    due = compute_next_scan_due(last_scan_at=last, cadence_days=30)
    assert due is not None and due < datetime.utcnow()
```

- [ ] **Step 3: Run it to confirm failure**

```bash
poetry run pytest backend/tests/test_client_list_service.py -v
```
Expected: FAIL — `ImportError: cannot import name 'compute_next_scan_due'`.

- [ ] **Step 4: Implement the helper and wire it in**

In `backend/app/services/client_list_service.py`, add the import `from datetime import datetime, timedelta` at the top, and:
```python
def compute_next_scan_due(last_scan_at: datetime | None, cadence_days: int) -> datetime | None:
    """Next-scan-due timestamp = last completed scan + cadence. None if never scanned."""
    if last_scan_at is None:
        return None
    return last_scan_at + timedelta(days=cadence_days)
```

In the item-building loop (lines 77-91), compute and pass the new fields. `latest.computed_at` is the last scan timestamp already used for `last_scan_at`:
```python
        last_scan_at = latest.computed_at if latest else None
        next_due = compute_next_scan_due(last_scan_at, c.scan_cadence_days)
        items.append(
            ClientListItem(
                **base,
                latest_overall_score=latest.overall_score if latest else None,
                last_scan_at=last_scan_at,
                previous_overall_score=previous.overall_score if previous else None,
                latest_scan_status=latest_scan.status if latest_scan else None,
                latest_scan_triggered_at=latest_scan.triggered_at if latest_scan else None,
                next_scan_due=next_due,
                is_scan_overdue=bool(next_due and next_due < datetime.utcnow()),
            )
        )
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
poetry run pytest backend/tests/test_client_list_service.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/client.py backend/app/services/client_list_service.py backend/tests/test_client_list_service.py
git commit -m "feat(backend): compute next_scan_due and overdue flag for client list"
```

### Task 2.3: Frontend — "scan due" badge + cadence setting

**Files:**
- Modify: `frontend/src/types/index.ts` (`ClientListItem`, `Client`)
- Modify: `frontend/src/components/clients/ClientCard.tsx`
- Modify: settings form (cadence number input) + `updateClient` union in `frontend/src/lib/api.ts`

- [ ] **Step 1: Extend types**

In `frontend/src/types/index.ts`: add `next_scan_due: string | null` and `is_scan_overdue: boolean` to `ClientListItem`; add `scan_cadence_days: number` to `Client`. Add `| "scan_cadence_days"` to the `updateClient` union in `api.ts`.

- [ ] **Step 2: Render the badge on the card**

In `frontend/src/components/clients/ClientCard.tsx`, when `client.is_scan_overdue` is true, render a small amber badge "Scan due" (reuse the existing badge/pill styling already in that card). When `next_scan_due` is set and not overdue, optionally show "Next scan: {formatted date}" in muted text.

- [ ] **Step 3: Add cadence control to settings**

Add a number input ("Review cadence (days)") to the settings form bound to `scan_cadence_days`, saved through the existing settings update action (extend it to pass `scan_cadence_days`).

- [ ] **Step 4: Verify compile**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): scan-due badge on client cards and cadence setting"
```

---

## Feature 3: Scan-to-Scan Diff ("Since last scan")

Compares the latest completed scan against the previous one and reports what changed: queries newly Seen by AI, queries newly Not seen by AI, and competitor visibility shifts. Pure post-processing of persisted `brand_detected` flags (purge-proof — no `response_text` needed).

### Task 3.1: Diff schema

**Files:**
- Modify: `backend/app/schemas/scan.py`

- [ ] **Step 1: Add response models**

Append to `backend/app/schemas/scan.py`:
```python
class ScanDiffQuery(BaseModel):
    platform: str
    category: str
    query_text: str

class ScanDiffResponse(BaseModel):
    latest_scan_id: uuid.UUID | None = None
    previous_scan_id: uuid.UUID | None = None
    latest_scan_at: datetime | None = None
    previous_scan_at: datetime | None = None
    # Visibility frequency (% of the client's own queries Seen by AI) for each scan.
    latest_visibility: float | None = None
    previous_visibility: float | None = None
    newly_seen: list[ScanDiffQuery] = []      # was Not seen, now Seen by AI
    newly_unseen: list[ScanDiffQuery] = []     # was Seen, now Not seen by AI
    has_comparison: bool = False               # False when there's no previous scan
```
Ensure `uuid`, `datetime`, and `BaseModel` are imported at the top of the file (match the existing imports there).

### Task 3.2: Diff service

**Files:**
- Create: `backend/app/services/scan_diff_service.py`
- Test: `backend/tests/test_scan_diff_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_scan_diff_service.py`. Use the existing DB-session test fixture pattern from `backend/tests/` (e.g. the `db` session fixture used by other service tests — match whatever fixture name those files use):
```python
import uuid
from datetime import datetime, timedelta

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.scan_diff_service import compute_scan_diff


def _client(db):
    c = Client(name="Diff Co", website="https://diff.example", industry="Dental")
    db.add(c); db.commit(); db.refresh(c)
    return c


def _scan(db, client_id, when):
    s = Scan(client_id=client_id, platform="multi", status="completed", completed_at=when)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _result(db, scan_id, query, detected):
    db.add(ScanQueryResult(
        scan_id=scan_id, platform="chatgpt", competitor_id=None,
        category="recommendation", query_text=query, response_text="x",
        brand_detected=detected,
    ))
    db.commit()


def test_diff_reports_newly_seen_and_unseen(db):
    c = _client(db)
    older = _scan(db, c.id, datetime.utcnow() - timedelta(days=7))
    _result(db, older.id, "q1", False)   # was not seen
    _result(db, older.id, "q2", True)    # was seen
    newer = _scan(db, c.id, datetime.utcnow())
    _result(db, newer.id, "q1", True)    # now seen      -> newly_seen
    _result(db, newer.id, "q2", False)   # now not seen  -> newly_unseen

    diff = compute_scan_diff(c.id, db)
    assert diff.has_comparison is True
    assert [q.query_text for q in diff.newly_seen] == ["q1"]
    assert [q.query_text for q in diff.newly_unseen] == ["q2"]


def test_diff_no_previous_scan(db):
    c = _client(db)
    only = _scan(db, c.id, datetime.utcnow())
    _result(db, only.id, "q1", True)
    diff = compute_scan_diff(c.id, db)
    assert diff.has_comparison is False
    assert diff.previous_scan_id is None
    assert diff.newly_seen == [] and diff.newly_unseen == []
```

- [ ] **Step 2: Run it to confirm failure**

```bash
poetry run pytest backend/tests/test_scan_diff_service.py -v
```
Expected: FAIL — module/function does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/scan_diff_service.py`:
```python
"""Scan-to-scan diff — what changed between the two most recent completed scans.

Compares the client's own query results (competitor_id IS NULL) matched by
(platform, category, query_text). Uses only persisted brand_detected flags, so
it survives the 90-day raw-response purge.
"""
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.scan import ScanDiffQuery, ScanDiffResponse


def _visibility(results: list[ScanQueryResult]) -> float | None:
    if not results:
        return None
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def compute_scan_diff(client_id: uuid.UUID, db: Session) -> ScanDiffResponse:
    scans = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .limit(2)
        .all()
    )
    if not scans:
        return ScanDiffResponse()

    latest = scans[0]
    previous = scans[1] if len(scans) > 1 else None

    def own_results(scan_id):
        return (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == scan_id,
                ScanQueryResult.competitor_id.is_(None),
            )
            .all()
        )

    latest_results = own_results(latest.id)

    if previous is None:
        return ScanDiffResponse(
            latest_scan_id=latest.id,
            latest_scan_at=latest.completed_at,
            latest_visibility=_visibility(latest_results),
            has_comparison=False,
        )

    previous_results = own_results(previous.id)
    prev_by_key = {
        (r.platform, r.category, r.query_text): r.brand_detected for r in previous_results
    }

    newly_seen: list[ScanDiffQuery] = []
    newly_unseen: list[ScanDiffQuery] = []
    for r in latest_results:
        key = (r.platform, r.category, r.query_text)
        if key not in prev_by_key:
            continue  # query didn't exist last scan (e.g. competitor added/removed)
        was = prev_by_key[key]
        if r.brand_detected and not was:
            newly_seen.append(ScanDiffQuery(platform=r.platform, category=r.category, query_text=r.query_text))
        elif not r.brand_detected and was:
            newly_unseen.append(ScanDiffQuery(platform=r.platform, category=r.category, query_text=r.query_text))

    return ScanDiffResponse(
        latest_scan_id=latest.id,
        previous_scan_id=previous.id,
        latest_scan_at=latest.completed_at,
        previous_scan_at=previous.completed_at,
        latest_visibility=_visibility(latest_results),
        previous_visibility=_visibility(previous_results),
        newly_seen=newly_seen,
        newly_unseen=newly_unseen,
        has_comparison=True,
    )
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
poetry run pytest backend/tests/test_scan_diff_service.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/scan.py backend/app/services/scan_diff_service.py backend/tests/test_scan_diff_service.py
git commit -m "feat(backend): scan-to-scan diff service"
```

### Task 3.3: Diff endpoint

**Files:**
- Modify: `backend/app/api/v1/scans.py`
- Test: `backend/tests/test_api_scans.py` (add to the existing file)

- [ ] **Step 1: Write the failing endpoint test**

Add a test that creates a client + two completed scans with results, then asserts `GET /api/v1/scans/client/{client_id}/diff` returns `has_comparison: true` and the expected `newly_seen`/`newly_unseen` query texts (reuse helpers/fixtures already present in `test_api_scans.py`).

- [ ] **Step 2: Run it to confirm failure (404)**

```bash
poetry run pytest backend/tests/test_api_scans.py -k diff -v
```
Expected: FAIL — route not found.

- [ ] **Step 3: Add the route**

In `backend/app/api/v1/scans.py`, import the service and schema and add (match the existing `require_api_key` dependency + `get_db` style in that router):
```python
from app.services.scan_diff_service import compute_scan_diff
from app.schemas.scan import ScanDiffResponse

@router.get(
    "/client/{client_id}/diff",
    response_model=ScanDiffResponse,
    dependencies=[Depends(require_api_key)],
)
def get_scan_diff(client_id: uuid.UUID, db: Session = Depends(get_db)):
    return compute_scan_diff(client_id, db)
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
poetry run pytest backend/tests/test_api_scans.py -k diff -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/scans.py backend/tests/test_api_scans.py
git commit -m "feat(backend): GET scan diff endpoint"
```

### Task 3.4: Frontend — "Since last scan" card

**Files:**
- Modify: `frontend/src/types/index.ts` (add `ScanDiffResponse`, `ScanDiffQuery`)
- Modify: `frontend/src/lib/api.ts` (add `getScanDiff`)
- Create: `frontend/src/components/scan/SinceLastScanCard.tsx`
- Modify: `frontend/src/app/clients/[id]/scan/page.tsx`

- [ ] **Step 1: Types**

Add to `frontend/src/types/index.ts`:
```typescript
export interface ScanDiffQuery { platform: string; category: string; query_text: string }
export interface ScanDiffResponse {
  latest_scan_id: string | null
  previous_scan_id: string | null
  latest_scan_at: string | null
  previous_scan_at: string | null
  latest_visibility: number | null
  previous_visibility: number | null
  newly_seen: ScanDiffQuery[]
  newly_unseen: ScanDiffQuery[]
  has_comparison: boolean
}
```

- [ ] **Step 2: API function**

In `frontend/src/lib/api.ts`, under the Scans section:
```typescript
export function getScanDiff(clientId: string): Promise<ScanDiffResponse> {
  return apiFetch<ScanDiffResponse>(`/api/v1/scans/client/${clientId}/diff`)
}
```
Add `ScanDiffResponse` to the type import on line 4.

- [ ] **Step 3: Build the card**

Create `frontend/src/components/scan/SinceLastScanCard.tsx`. Props: `diff: ScanDiffResponse`. If `!has_comparison`, render a muted "First scan — no comparison yet." Otherwise show: visibility change (`latest_visibility` vs `previous_visibility`) using approved language ("Visibility frequency: 62% → 71%"), a green-tinted list "Newly Seen by AI" (`newly_seen`), and an amber/red list "Now Not seen by AI" (`newly_unseen`). Use existing card styling from sibling scan components.

- [ ] **Step 4: Render on the scan page**

In `frontend/src/app/clients/[id]/scan/page.tsx` (a server component), call `getScanDiff(id)` alongside the existing data fetches and render `<SinceLastScanCard diff={diff} />` near the top of the results.

- [ ] **Step 5: Verify compile**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): Since last scan diff card on scan page"
```

---

## Feature 4: Sentiment Rating on AI Responses

When the brand is Seen by AI, classify how it's described: `positive` / `neutral` / `negative`. Adds one Claude (Haiku) call per detected mention, isolated like position extraction (failure → `sentiment=None`, never fails the scan), and cost-tracked through the existing registry.

### Task 4.1: `sentiment` column on ScanQueryResult

**Files:**
- Modify: `backend/app/models/scan_query_result.py`
- Create: `backend/alembic/versions/<generated>_add_sentiment_to_scan_query_results.py`

- [ ] **Step 1: Add the column**

In `backend/app/models/scan_query_result.py`, after `recommendation_position` (line 23):
```python
    # How AI describes the brand when Seen: "positive" | "neutral" | "negative".
    # Null when the brand was Not seen, or when classification failed/was skipped.
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

- [ ] **Step 2: Generate + fill migration**

`poetry run alembic revision -m "add sentiment to scan_query_results"`, then:
```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("scan_query_results", sa.Column("sentiment", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("scan_query_results", "sentiment")
```

- [ ] **Step 3: Apply + commit**

```bash
poetry run alembic upgrade head
git add backend/app/models/scan_query_result.py backend/alembic/versions/
git commit -m "feat(backend): add sentiment column to scan_query_results"
```

### Task 4.2: Sentiment prompt + registry entry

**Files:**
- Create: `backend/app/prompts/sentiment.py`
- Modify: `backend/app/prompts/registry.py`

- [ ] **Step 1: Create the prompt module**

`backend/app/prompts/sentiment.py`:
```python
"""Prompt template for classifying how an AI response describes the brand."""

VERSION = "v1"

VALID = ("positive", "neutral", "negative")


def build_prompt(brand_name: str, response_text: str) -> str:
    return (
        "You are a strict sentiment classifier. A user asked an AI assistant a question "
        f"and it produced the response below, which mentions the business '{brand_name}'. "
        "Classify ONLY how the response describes that business, in one word: "
        "positive, neutral, or negative. Reply with exactly one of those three words and nothing else.\n\n"
        f"RESPONSE:\n{response_text[:4000]}"
    )
```

- [ ] **Step 2: Register it**

In `backend/app/prompts/registry.py`: add `sentiment` to the `from app.prompts import (...)` block, and add to `REGISTRY`:
```python
    "sentiment_classify":          {"version": sentiment.VERSION,                 "model": MODEL},
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/prompts/sentiment.py backend/app/prompts/registry.py
git commit -m "feat(backend): add sentiment classification prompt + registry entry"
```

### Task 4.3: Sentiment service

**Files:**
- Create: `backend/app/services/sentiment_service.py`
- Test: `backend/tests/test_sentiment_service.py`

- [ ] **Step 1: Write the failing test (mock Anthropic, no network)**

Create `backend/tests/test_sentiment_service.py`:
```python
from types import SimpleNamespace
from unittest.mock import patch

from app.services.sentiment_service import classify_sentiment


def _resp(text):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=1),
    )


def test_classify_returns_normalized_label():
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: _resp("Positive.")))
    with patch("app.services.sentiment_service.anthropic_client", return_value=fake):
        assert classify_sentiment("Acme", "Acme is excellent.") == "positive"


def test_classify_unrecognized_output_returns_none():
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: _resp("I am not sure")))
    with patch("app.services.sentiment_service.anthropic_client", return_value=fake):
        assert classify_sentiment("Acme", "...") is None
```

- [ ] **Step 2: Run it to confirm failure**

```bash
poetry run pytest backend/tests/test_sentiment_service.py -v
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/sentiment_service.py`:
```python
"""Classify how an AI response describes the brand. Best-effort: returns None on
any failure so the scan never breaks. Cost-tracked via cost_tracker."""
import uuid

import structlog

from app.prompts import sentiment as sentiment_prompt
from app.services.claude_client import MODEL, anthropic_client
from app.services.cost_tracker import record_llm_call

logger = structlog.get_logger()


def classify_sentiment(
    brand_name: str,
    response_text: str,
    client_id: uuid.UUID | None = None,
) -> str | None:
    if not response_text:
        return None
    try:
        resp = anthropic_client().messages.create(
            model=MODEL,
            max_tokens=5,
            messages=[{"role": "user", "content": sentiment_prompt.build_prompt(brand_name, response_text)}],
        )
        record_llm_call(service="sentiment_classify", model=MODEL, response=resp, client_id=client_id)
        word = resp.content[0].text.strip().lower().strip(".")
        return word if word in sentiment_prompt.VALID else None
    except Exception as exc:
        logger.warning("sentiment_classify_failed", error=str(exc))
        return None
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
poetry run pytest backend/tests/test_sentiment_service.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sentiment_service.py backend/tests/test_sentiment_service.py
git commit -m "feat(backend): sentiment classification service with cost tracking"
```

### Task 4.4: Wire sentiment into the scan engine

**Files:**
- Modify: `backend/app/services/scan_service.py:82-111` (client-query loop in `_run_platform_queries`)

- [ ] **Step 1: Add the call alongside position extraction**

In `_run_platform_queries`, inside the client-query loop, after the position block (line 99) and before building the `ScanQueryResult`, add:
```python
        sentiment = None
        if detected:
            from app.services.sentiment_service import classify_sentiment
            sentiment = classify_sentiment(client.name, response_text, client.id)
```
Then add `sentiment=sentiment,` to the `ScanQueryResult(...)` constructor for client queries (lines 101-110). **Do not** classify competitor queries (leave those rows' sentiment null).

Note: this loop runs in worker threads with no DB session; `record_llm_call` is called with `db=None` inside the service, so it opens its own session — safe under concurrency.

- [ ] **Step 2: Run the existing scan tests to confirm no regression**

```bash
poetry run pytest backend/tests/ -k scan -v
```
Expected: PASS (sentiment defaults to null when the platform clients are mocked and brand isn't "detected", or the Anthropic call is mocked/raises and is swallowed).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scan_service.py
git commit -m "feat(backend): classify sentiment for detected brand mentions during scan"
```

### Task 4.5: Surface sentiment in scan results (admin only)

**Files:**
- Modify: `backend/app/schemas/scan.py` (the per-result schema returned to admin)
- Modify: `frontend/src/types/index.ts`
- Modify: the scan results table component under `frontend/src/components/scan/`

- [ ] **Step 1: Add `sentiment` to the admin scan-result schema**

In `backend/app/schemas/scan.py`, add `sentiment: str | None = None` to the result model that the admin scan endpoint returns (the one populated from `ScanQueryResult`). **Confirm the client-view scan schema in `app/schemas/client_view.py` does NOT gain this field.**

- [ ] **Step 2: Render a sentiment badge (admin)**

Add `sentiment?: "positive" | "neutral" | "negative" | null` to the scan-result type in `frontend/src/types/index.ts`, and in the admin scan results row render a small badge (green=positive, slate=neutral, red=negative) only when the brand was Seen and `sentiment` is set. Keep it on admin surfaces only.

- [ ] **Step 3: Verify + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add backend/app/schemas/scan.py frontend/src
git commit -m "feat: surface AI-response sentiment on admin scan results"
```

---

## Feature 5: Competitor Gap Matrix (cross-client)

A portfolio-level grid: for each (real, non-archived) client and each win/loss query category, is the client winning or are competitors winning? Surfaces patterns across the whole book of business. Read-only, computed on demand. **Adds a new admin page → CLAUDE.md §9 must be updated.**

### Task 5.1: Gap matrix schema + service

**Files:**
- Create: `backend/app/schemas/gap_matrix.py`
- Create: `backend/app/services/gap_matrix_service.py`
- Test: `backend/tests/test_gap_matrix_service.py`

- [ ] **Step 1: Schema**

`backend/app/schemas/gap_matrix.py`:
```python
import uuid
from pydantic import BaseModel

# Per (client, category): client visibility vs the best competitor's visibility.
class GapCell(BaseModel):
    category: str
    client_visibility: float | None = None       # % of the client's queries Seen by AI
    top_competitor_visibility: float | None = None
    top_competitor_name: str | None = None
    competitors_winning: bool = False             # a competitor beats the client here

class GapMatrixRow(BaseModel):
    client_id: uuid.UUID
    client_name: str
    cells: list[GapCell] = []

class GapMatrixResponse(BaseModel):
    categories: list[str] = []
    rows: list[GapMatrixRow] = []
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_gap_matrix_service.py` — create one non-prospect client with a completed scan where, for `recommendation`, the client is Not seen but a competitor is Seen; assert that client's `recommendation` cell has `competitors_winning is True`. (Reuse the `db` fixture and the ScanQueryResult/Competitor construction style from `test_scan_diff_service.py` / `test_gap_matrix_service.py` siblings.)

- [ ] **Step 3: Run to confirm failure**

```bash
poetry run pytest backend/tests/test_gap_matrix_service.py -v
```
Expected: FAIL — module does not exist.

- [ ] **Step 4: Implement the service**

`backend/app/services/gap_matrix_service.py` — iterate non-archived, non-prospect clients; for each, load the latest completed scan's results; per `WIN_LOSS_CATEGORIES` category compute the client's visibility (% of own rows `brand_detected`) and each competitor's visibility (rows with that `competitor_id`), take the top competitor, and set `competitors_winning = top_competitor_visibility > client_visibility`. Reuse `visibility_by_platform`'s counting idea but group by category. Return `GapMatrixResponse(categories=list(WIN_LOSS_CATEGORIES), rows=[...])`.

```python
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import WIN_LOSS_CATEGORIES
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.gap_matrix import GapCell, GapMatrixResponse, GapMatrixRow


def _visibility(results) -> float | None:
    if not results:
        return None
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def compute_gap_matrix(db: Session) -> GapMatrixResponse:
    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None), Client.is_prospect.is_(False))
        .order_by(Client.name)
        .all()
    )
    rows: list[GapMatrixRow] = []
    for c in clients:
        latest = (
            db.query(Scan)
            .filter(Scan.client_id == c.id, Scan.status == "completed")
            .order_by(desc(Scan.completed_at), desc(Scan.id))
            .first()
        )
        cells: list[GapCell] = []
        if latest:
            competitors = {comp.id: comp.name for comp in db.query(Competitor).filter(Competitor.client_id == c.id).all()}
            results = db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == latest.id).all()
            for category in WIN_LOSS_CATEGORIES:
                cat = [r for r in results if r.category == category]
                client_vis = _visibility([r for r in cat if r.competitor_id is None])
                best_name, best_vis = None, None
                for comp_id, comp_name in competitors.items():
                    v = _visibility([r for r in cat if r.competitor_id == comp_id])
                    if v is not None and (best_vis is None or v > best_vis):
                        best_name, best_vis = comp_name, v
                cells.append(GapCell(
                    category=category,
                    client_visibility=client_vis,
                    top_competitor_visibility=best_vis,
                    top_competitor_name=best_name,
                    competitors_winning=bool(best_vis is not None and (client_vis is None or best_vis > client_vis)),
                ))
        rows.append(GapMatrixRow(client_id=c.id, client_name=c.name, cells=cells))
    return GapMatrixResponse(categories=list(WIN_LOSS_CATEGORIES), rows=rows)
```

- [ ] **Step 5: Run to confirm pass, then commit**

```bash
poetry run pytest backend/tests/test_gap_matrix_service.py -v
git add backend/app/schemas/gap_matrix.py backend/app/services/gap_matrix_service.py backend/tests/test_gap_matrix_service.py
git commit -m "feat(backend): cross-client competitor gap matrix service"
```

### Task 5.2: Gap matrix endpoint

**Files:**
- Modify: `backend/app/api/v1/clients.py`
- Test: `backend/tests/test_api_clients.py`

- [ ] **Step 1: Failing test** — assert `GET /api/v1/clients/gap-matrix` returns 200 with `categories` and `rows`. **Note:** this static path must be registered before the dynamic `/{client_id}` route is matched; FastAPI matches by registration order, so place this route ABOVE `get_client`. Add the test first; expect 404/422 (the path collides with `/{client_id}` parsing) until the route exists.

- [ ] **Step 2: Add the route ABOVE `@router.get("/{client_id}")`**

In `backend/app/api/v1/clients.py`, before `get_client` (line 74):
```python
from app.services.gap_matrix_service import compute_gap_matrix
from app.schemas.gap_matrix import GapMatrixResponse

@router.get(
    "/gap-matrix",
    response_model=GapMatrixResponse,
    dependencies=[Depends(require_api_key)],
)
def get_gap_matrix(db: Session = Depends(get_db)):
    return compute_gap_matrix(db)
```

- [ ] **Step 3: Run the test to confirm pass**

```bash
poetry run pytest backend/tests/test_api_clients.py -k gap_matrix -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/clients.py backend/tests/test_api_clients.py
git commit -m "feat(backend): GET cross-client gap matrix endpoint"
```

### Task 5.3: Frontend page + nav doc update

**Files:**
- Modify: `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`
- Create: `frontend/src/app/clients/gap-matrix/page.tsx`
- Create: `frontend/src/components/clients/GapMatrixTable.tsx`
- Modify: `CLAUDE.md` §9 (navigation list)
- Modify: the `/clients` page header to add a link to the matrix

- [ ] **Step 1: Types + API**

Add `GapCell`, `GapMatrixRow`, `GapMatrixResponse` to `types/index.ts`. Add to `api.ts`:
```typescript
export function getGapMatrix(): Promise<GapMatrixResponse> {
  return apiFetch<GapMatrixResponse>(`/api/v1/clients/gap-matrix`)
}
```

- [ ] **Step 2: Build the table component**

`GapMatrixTable.tsx`: rows = clients, columns = categories. Each cell shows the client's visibility frequency and, when `competitors_winning`, a red highlight with "Your competitors are winning here" (approved §2 phrasing) and the `top_competitor_name`. Green when the client leads. Muted "—" when no scan yet.

- [ ] **Step 3: Build the page**

`frontend/src/app/clients/gap-matrix/page.tsx` (server component): `const matrix = await getGapMatrix()`, render a heading "Competitor Gap Matrix" + `<GapMatrixTable matrix={matrix} />`. Because `gap-matrix` is a static segment, Next.js routes it before `[id]` — no collision.

- [ ] **Step 4: Add a link from /clients**

In `ClientsManager.tsx` header actions (near `AddProspectButton`/`AddClientButton`, line 116-119), add a `Link` button to `/clients/gap-matrix` labelled "Gap matrix".

- [ ] **Step 5: Update CLAUDE.md §9**

In `CLAUDE.md`, under "Admin Panel Navigation", add the line:
```
/clients/gap-matrix      → cross-client competitor gap matrix
```

- [ ] **Step 6: Verify + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src CLAUDE.md
git commit -m "feat(frontend): cross-client competitor gap matrix page + nav doc"
```

---

## Feature 6: Shareable Scan Snippet (no LLM)

A client-safe PNG card rendering a verbatim excerpt of one "Seen by AI" response — "Here's what ChatGPT said about you." Built with Pillow (already installed). Competitor names redacted; brand text verbatim. No LLM call.

### Task 6.1: Snippet builder (text selection + redaction)

**Files:**
- Create: `backend/app/services/snippet_service.py`
- Test: `backend/tests/test_snippet_service.py`
- Add asset: `backend/app/assets/fonts/Inter-Regular.ttf` and `Inter-Bold.ttf` (download from the Inter release; see step note)

- [ ] **Step 1: Write the failing test for excerpt selection + redaction**

`backend/tests/test_snippet_service.py`:
```python
from app.services.snippet_service import build_excerpt


def test_excerpt_picks_sentence_with_brand_and_redacts_competitors():
    text = (
        "There are many options. Acme Dental is widely regarded as the best clinic in KL. "
        "Some people also like RivalCo."
    )
    excerpt = build_excerpt(text, brand="Acme Dental", competitors=["RivalCo"])
    assert "Acme Dental" in excerpt
    assert "RivalCo" not in excerpt
    assert excerpt.endswith(".") or len(excerpt) <= 280


def test_excerpt_returns_none_when_brand_absent():
    assert build_excerpt("No mention here.", brand="Acme", competitors=[]) is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest backend/tests/test_snippet_service.py -v
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `build_excerpt` (pure text, no Pillow yet)**

In `backend/app/services/snippet_service.py`:
```python
"""Build a client-safe PNG snippet of one 'Seen by AI' response.

Text is verbatim except competitor names, which are redacted to '[a competitor]'
so a client-facing card never advertises a rival. No LLM is used.
"""
import re
from pathlib import Path

_MAX_EXCERPT_CHARS = 280
_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _redact(text: str, competitors: list[str]) -> str:
    for name in sorted([c for c in competitors if c], key=len, reverse=True):
        text = re.sub(re.escape(name), "[a competitor]", text, flags=re.IGNORECASE)
    return text


def build_excerpt(response_text: str, brand: str, competitors: list[str]) -> str | None:
    """Return the sentence containing the brand (redacted, truncated), or None."""
    if not response_text or brand.lower() not in response_text.lower():
        return None
    sentences = re.split(r"(?<=[.!?])\s+", response_text.strip())
    chosen = next((s for s in sentences if brand.lower() in s.lower()), None)
    if chosen is None:
        return None
    chosen = _redact(chosen.strip(), competitors)
    if len(chosen) > _MAX_EXCERPT_CHARS:
        chosen = chosen[: _MAX_EXCERPT_CHARS - 1].rstrip() + "…"
    return chosen
```

- [ ] **Step 4: Run to confirm pass**

```bash
poetry run pytest backend/tests/test_snippet_service.py -v
```
Expected: PASS

- [ ] **Step 5: Add the font asset**

Create `backend/app/assets/fonts/` and add `Inter-Regular.ttf` + `Inter-Bold.ttf` (Inter is OFL-licensed). Commit the TTFs. (The renderer falls back to `ImageFont.load_default()` if absent, but quality is poor — ship the fonts.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/snippet_service.py backend/tests/test_snippet_service.py backend/app/assets/fonts/
git commit -m "feat(backend): scan snippet excerpt builder with competitor redaction"
```

### Task 6.2: Pillow renderer

**Files:**
- Modify: `backend/app/services/snippet_service.py`
- Test: `backend/tests/test_snippet_service.py`

- [ ] **Step 1: Write the failing test (asserts PNG bytes)**

Add:
```python
def test_render_snippet_png_returns_png_bytes():
    from app.services.snippet_service import render_snippet_png
    png = render_snippet_png(
        platform_label="ChatGPT",
        brand="Acme Dental",
        excerpt="Acme Dental is widely regarded as the best clinic in KL.",
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number
    assert len(png) > 1000
```

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest backend/tests/test_snippet_service.py -k render -v
```
Expected: FAIL — `render_snippet_png` not defined.

- [ ] **Step 3: Implement the renderer**

Append to `backend/app/services/snippet_service.py`:
```python
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

_W, _H = 1200, 630           # social-card dimensions
_BG = (15, 23, 42)           # slate-900
_FG = (241, 245, 249)        # slate-100
_ACCENT = (74, 222, 128)     # green-400 — "Seen by AI"


def _font(name: str, size: int):
    path = _FONT_DIR / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines


def render_snippet_png(platform_label: str, brand: str, excerpt: str) -> bytes:
    img = Image.new("RGB", (_W, _H), _BG)
    draw = ImageDraw.Draw(img)

    draw.text((80, 70), "SEEN BY AI", font=_font("Inter-Bold.ttf", 34), fill=_ACCENT)
    draw.text((80, 120), f"What {platform_label} said about {brand}", font=_font("Inter-Bold.ttf", 48), fill=_FG)

    body = _font("Inter-Regular.ttf", 40)
    y = 240
    for line in _wrap(draw, f"“{excerpt}”", body, _W - 160):
        draw.text((80, y), line, font=body, fill=_FG)
        y += 56

    draw.text((80, _H - 80), "Tracked by SeenBy", font=_font("Inter-Regular.ttf", 28), fill=(148, 163, 184))

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 4: Run to confirm pass, then commit**

```bash
poetry run pytest backend/tests/test_snippet_service.py -v
git add backend/app/services/snippet_service.py backend/tests/test_snippet_service.py
git commit -m "feat(backend): Pillow renderer for scan snippet card"
```

### Task 6.3: Snippet endpoint

**Files:**
- Modify: `backend/app/api/v1/scans.py`
- Test: `backend/tests/test_api_scans.py`

- [ ] **Step 1: Failing test** — seed a scan result where the brand is detected with a `response_text` containing the brand; assert `GET /api/v1/scans/{scan_id}/results/{result_id}/snippet.png` returns 200 with `content-type: image/png` and PNG-magic bytes. Assert a 404 when the result's brand was Not seen / no usable excerpt.

- [ ] **Step 2: Run to confirm failure**

```bash
poetry run pytest backend/tests/test_api_scans.py -k snippet -v
```
Expected: FAIL — route not found.

- [ ] **Step 3: Add the route**

In `backend/app/api/v1/scans.py` (import `Response` from `fastapi`, `PLATFORM_LABELS` from constants, the `Client`/`Competitor`/`ScanQueryResult` models, and `snippet_service`):
```python
from fastapi import Response
from app.core.constants import PLATFORM_LABELS
from app.services import snippet_service

@router.get(
    "/{scan_id}/results/{result_id}/snippet.png",
    dependencies=[Depends(require_api_key)],
)
def get_result_snippet(scan_id: uuid.UUID, result_id: uuid.UUID, db: Session = Depends(get_db)):
    result = db.get(ScanQueryResult, result_id)
    if not result or result.scan_id != scan_id or result.competitor_id is not None:
        raise HTTPException(status_code=404, detail="Result not found")
    scan = db.get(Scan, scan_id)
    client = db.get(Client, scan.client_id) if scan else None
    if not client:
        raise HTTPException(status_code=404, detail="Result not found")
    competitors = [c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()]
    excerpt = snippet_service.build_excerpt(result.response_text or "", client.name, competitors)
    if not excerpt:
        raise HTTPException(status_code=404, detail="No shareable excerpt for this result")
    png = snippet_service.render_snippet_png(
        platform_label=PLATFORM_LABELS.get(result.platform, result.platform),
        brand=client.name,
        excerpt=excerpt,
    )
    return Response(content=png, media_type="image/png")
```

- [ ] **Step 4: Run to confirm pass, then commit**

```bash
poetry run pytest backend/tests/test_api_scans.py -k snippet -v
git add backend/app/api/v1/scans.py backend/tests/test_api_scans.py
git commit -m "feat(backend): scan snippet PNG endpoint"
```

### Task 6.4: Frontend — "Share this result" button

**Files:**
- Modify: scan results row/table component under `frontend/src/components/scan/`
- (No `api.ts` change — the image is fetched by URL through a proxy route)
- Create: `frontend/src/app/clients/[id]/scan/snippet/[scanId]/[resultId]/route.ts` (proxy that streams the PNG with the server-side API key)

- [ ] **Step 1: Add a proxy route (keeps the admin API key server-side)**

The PNG endpoint requires the admin bearer token, which must never reach the browser. Create a Next.js route handler that fetches the backend PNG with the server key and streams it back:
```typescript
// frontend/src/app/clients/[id]/scan/snippet/[scanId]/[resultId]/route.ts
import { NextRequest } from "next/server"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ scanId: string; resultId: string }> }) {
  const { scanId, resultId } = await params
  const base = process.env.API_BASE_URL ?? "http://localhost:8000"
  const res = await fetch(`${base}/api/v1/scans/${scanId}/results/${resultId}/snippet.png`, {
    headers: { Authorization: `Bearer ${process.env.ADMIN_API_KEY}` },
    cache: "no-store",
  })
  if (!res.ok) return new Response("Not found", { status: 404 })
  return new Response(res.body, { headers: { "Content-Type": "image/png" } })
}
```

- [ ] **Step 2: Add the button**

On each "Seen by AI" scan result row, add a "Share image" button that opens `/clients/{clientId}/scan/snippet/{scanId}/{resultId}` in a new tab (preview + right-click save) or triggers a download. Only show it when the row's brand was Seen.

- [ ] **Step 3: Verify + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit
git add frontend/src
git commit -m "feat(frontend): share scan-result snippet image via server proxy"
```

---

## Self-Review

**Spec coverage** — all six features mapped: (1) Internal notes → Tasks 1.1-1.3; (2) Scan reminder → 2.1-2.3; (3) Scan diff → 3.1-3.4; (4) Sentiment → 4.1-4.5; (5) Gap matrix → 5.1-5.3; (6) Snippet → 6.1-6.4.

**Language rules** — diff card (3.4), gap matrix (5.3), and snippet (6.x) are the client-facing/approved-language surfaces; each task specifies "Seen by AI" / "visibility frequency" / "Your competitors are winning here". Sentiment and notes are explicitly fenced off from the client view.

**Schema/migration discipline** — three columns, three separate migrations, each generated via `alembic revision -m` (no hardcoded `down_revision`).

**Type consistency** — `compute_next_scan_due(last_scan_at, cadence_days)` signature matches between Task 2.2 impl and its test; `ScanDiffResponse` field names match across schema (3.1), service (3.2), endpoint (3.3), and frontend type (3.4); `build_excerpt(response_text, brand, competitors)` and `render_snippet_png(platform_label, brand, excerpt)` signatures match across 6.1/6.2/6.3.

**Known integration risks flagged in-line:** (a) the gap-matrix route must be registered above `/{client_id}` (Task 5.2); (b) the snippet PNG must be proxied so the admin key stays server-side (Task 6.4); (c) sentiment runs inside threadpool workers with no DB session, so `record_llm_call` uses its own session (Task 4.4).

**Open item for the implementer:** confirm the exact pytest DB-session fixture name in `backend/tests/` (referred to as `db`, `client`, `auth_headers` here) and align new tests to it before writing — fixtures are defined in `backend/tests/conftest.py`.
