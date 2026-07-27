# Review Queue — Cross-Client Work-Log Inbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin one page listing every pending work-log suggestion across all clients, editable in place, with publish/dismiss — so delivered work stops going unproven because a suggestion was never found.

**Architecture:** Two new admin-only **read** endpoints on a global `/work-log` router return suggestions carrying their client identity. Publish/dismiss reuse the existing per-client `PATCH /clients/{client_id}/work-log/{entry_id}` — no second mutation path into the table. The frontend gains a `(admin)` route group so global pages sit at the top level while sharing the existing sidebar + auth layout.

**Tech Stack:** FastAPI + SQLAlchemy (no migration — no schema change), Next.js 15 App Router, shadcn/ui, server actions.

**Spec:** `docs/superpowers/specs/2026-07-27-review-queue-design.md`

## Global Constraints

- **No new mutation surface.** Writes go through the existing `PATCH /clients/{client_id}/work-log/{entry_id}` only. That route already 404s when the entry does not belong to the client in the URL; keeping it as the sole write path means the ownership guard stays exercised and there is no second validation implementation to drift. (Phase 4's worst bug was two code paths populating one response model and disagreeing.)
- **No migration, no model change.** `WorkLogEntry` already has `client_id`. Nothing in this plan touches Alembic. Current single head is `de87b61a859c` and must stay that way.
- **No score, dimension, or `SCORE_VERSION` change.**
- **Status filtered at the query,** never merely omitted from a schema — same rule the client-view surface follows.
- **Archived clients excluded** at the query, matching `_get_client_or_404`'s existing `archived_at is not None` behaviour.
- **The badge must never break the sidebar.** The sidebar renders on every admin page; a throwing count fetch there takes down the whole panel. Catch, default to 0, render no badge (CLAUDE.md §10 best-effort pattern).
- **Language rules (CLAUDE.md §2)** apply to every string. Descriptions are already sanitised by `suggest()` at write time and by `update_entry()` on edit — no new sanitising logic needed, but no new copy may use banned vocabulary.
- **Admin-only** (`Depends(require_api_key)`) on both new routes.
- **No "publish all", no multi-select, no publish keyboard shortcut** — spec §7. This is a deliberate omission; see that section before adding one.
- Frontend: shadcn/ui only; all API calls through `src/lib/api.ts`; types in `src/types/index.ts`.
- Backend commands (this machine): poetry at `C:\Users\IrfanFaris\AppData\Roaming\Python\Scripts\poetry.exe`, run from `backend/`. ⚠️ `backend/.env` DATABASE_URL points at PROD Supabase — **never** run `alembic upgrade`. This plan needs no Alembic command at all.
- ⚠️ **Never run `npm run build` while `npm run dev` is running.** `next build` overwrites the `.next/` the dev server is serving from and leaves the app rendering unstyled. Stop the dev server before any build step.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/services/work_log_service.py` (modify) | Add `suggested_across_clients` + `suggested_count` |
| `backend/app/schemas/work_log.py` (modify) | Add `WorkLogSuggestionOut` extending `WorkLogEntryOut` |
| `backend/app/api/v1/work_log_global.py` (new) | Global read router, prefix `/work-log` |
| `backend/app/api/v1/router.py` (modify) | Register the new router |
| `backend/tests/test_work_log_global.py` (new) | Service + route tests |
| `frontend/src/types/index.ts` (modify) | `WorkLogSuggestion` type |
| `frontend/src/lib/api.ts` (modify) | `getSuggestedWorkLog`, `getSuggestedWorkLogCount` |
| `frontend/src/app/(admin)/layout.tsx` (moved from `clients/layout.tsx`) | Shared admin shell + auth guard + badge count fetch |
| `frontend/src/app/(admin)/clients/**` (moved) | Unchanged pages, new location |
| `frontend/src/app/(admin)/gap-matrix/page.tsx` (moved) | Unchanged page, now top-level URL |
| `frontend/src/app/(admin)/review-queue/page.tsx` (new) | Server component: fetch suggestions |
| `frontend/src/app/(admin)/review-queue/ReviewQueueClient.tsx` (new) | Client component: grouping, inline edit, actions |
| `frontend/src/app/(admin)/review-queue/actions.ts` (new) | Server actions wrapping the existing PATCH |
| `frontend/src/components/layout/Sidebar.tsx` (modify) | `GLOBAL_NAV` + badge + gap-matrix href |
| `frontend/next.config.ts` (modify) | Redirect `/clients/gap-matrix` → `/gap-matrix` |
| `CLAUDE.md` (modify) | §9 nav structure |

---

### Task 1: Service — cross-client suggested queries

**Files:**
- Modify: `backend/app/services/work_log_service.py`
- Test: `backend/tests/test_work_log_global.py` (new)

**Interfaces:**
- Consumes: existing `WorkLogEntry` model, `suggest()`, `update_entry()`.
- Produces: `suggested_across_clients(db: Session) -> list[tuple[WorkLogEntry, Client]]` and `suggested_count(db: Session) -> int`. Task 2 calls both.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_work_log_global.py`:

```python
"""Cross-client work-log queue (spec §3.1, §6). Mirrors test_work_log_api.py's
fixtures — conftest.py provides only `db` (a real in-memory SQLite session).
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    from app.main import app
    from app.core.database import get_db

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from app.core.config import settings
    return {"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}


def _make_client(db, name="Acme Dental", archived=False):
    from app.core.time import utcnow
    from app.models.client import Client
    c = Client(name=name, website=f"https://{name.replace(' ', '').lower()}.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    if archived:
        c.archived_at = utcnow()
    db.add(c)
    db.commit()
    return c


def test_suggested_across_clients_spans_clients_and_carries_client(db):
    from app.services import work_log_service
    a = _make_client(db, "Acme Dental")
    b = _make_client(db, "Bravo Legal")
    work_log_service.suggest(a.id, "technical", "Acme thing", "r:a", db)
    work_log_service.suggest(b.id, "content", "Bravo thing", "r:b", db)

    rows = work_log_service.suggested_across_clients(db)
    assert len(rows) == 2
    pairs = {(c.name, e.description) for e, c in rows}
    assert pairs == {("Acme Dental", "Acme thing"), ("Bravo Legal", "Bravo thing")}


def test_suggested_excludes_published_and_dismissed(db):
    from app.services import work_log_service
    c = _make_client(db)
    keep = work_log_service.suggest(c.id, "technical", "Still pending", "r:1", db)
    pub = work_log_service.suggest(c.id, "content", "Published", "r:2", db)
    work_log_service.update_entry(pub, {"status": "published"}, db)
    dis = work_log_service.suggest(c.id, "content", "Dismissed", "r:3", db)
    work_log_service.update_entry(dis, {"status": "dismissed"}, db)

    rows = work_log_service.suggested_across_clients(db)
    assert [e.id for e, _ in rows] == [keep.id]


def test_suggested_excludes_archived_clients(db):
    from app.services import work_log_service
    live = _make_client(db, "Live Client")
    gone = _make_client(db, "Archived Client", archived=True)
    work_log_service.suggest(live.id, "technical", "Visible", "r:1", db)
    work_log_service.suggest(gone.id, "technical", "Hidden", "r:2", db)

    rows = work_log_service.suggested_across_clients(db)
    assert [e.description for e, _ in rows] == ["Visible"]
    assert work_log_service.suggested_count(db) == 1


def test_suggested_count_matches_list_length(db):
    from app.services import work_log_service
    a = _make_client(db, "Acme Dental")
    b = _make_client(db, "Bravo Legal")
    for i in range(3):
        work_log_service.suggest(a.id, "technical", f"A{i}", f"r:a{i}", db)
    work_log_service.suggest(b.id, "content", "B0", "r:b0", db)

    assert work_log_service.suggested_count(db) == len(
        work_log_service.suggested_across_clients(db)) == 4


def test_suggested_grouped_by_client_then_newest_first(db):
    from app.services import work_log_service
    today = date.today()
    b = _make_client(db, "Bravo Legal")
    a = _make_client(db, "Acme Dental")
    work_log_service.suggest(b.id, "content", "B old", "r:b1", db,
                             entry_date=today - timedelta(days=5))
    work_log_service.suggest(a.id, "technical", "A new", "r:a1", db, entry_date=today)
    work_log_service.suggest(a.id, "technical", "A old", "r:a2", db,
                             entry_date=today - timedelta(days=2))

    rows = work_log_service.suggested_across_clients(db)
    # Client name ascending, then newest entry_date first inside each client.
    assert [(c.name, e.description) for e, c in rows] == [
        ("Acme Dental", "A new"),
        ("Acme Dental", "A old"),
        ("Bravo Legal", "B old"),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `backend/`:
```bash
poetry run pytest tests/test_work_log_global.py -q
```
Expected: FAIL — `AttributeError: module 'app.services.work_log_service' has no attribute 'suggested_across_clients'`.

- [ ] **Step 3: Add the Client import**

In `backend/app/services/work_log_service.py`, the existing model import block reads:

```python
from app.models.work_log_entry import WorkLogEntry
```

Add `Client` alongside it:

```python
from app.models.client import Client
from app.models.work_log_entry import WorkLogEntry
```

(Models never import services, so this cannot create a cycle.)

- [ ] **Step 4: Implement both functions**

Append to `backend/app/services/work_log_service.py`, after the existing `published_count_since`:

```python
def suggested_across_clients(db: Session) -> list[tuple[WorkLogEntry, Client]]:
    """Every pending suggestion across all live clients, for the Review Queue.

    Status is filtered HERE, at the query — a `published` or `dismissed` row must
    never reach the queue. Archived clients are excluded to match the per-client
    routes' `_get_client_or_404` behaviour. Ordering is client name then newest
    first, so the page groups cleanly and does not reshuffle between refreshes.
    """
    return (
        db.query(WorkLogEntry, Client)
        .join(Client, Client.id == WorkLogEntry.client_id)
        .filter(WorkLogEntry.status == "suggested", Client.archived_at.is_(None))
        .order_by(Client.name, desc(WorkLogEntry.entry_date), desc(WorkLogEntry.created_at))
        .all()
    )


def suggested_count(db: Session) -> int:
    """Count for the sidebar badge.

    Deliberately a COUNT, not len(suggested_across_clients(db)) — this runs on
    every admin page load. Same lesson as has_published(): never hydrate rows to
    produce a number.
    """
    return (
        db.query(WorkLogEntry.id)
        .join(Client, Client.id == WorkLogEntry.client_id)
        .filter(WorkLogEntry.status == "suggested", Client.archived_at.is_(None))
        .count()
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_work_log_global.py -q
```
Expected: 5 passed.

- [ ] **Step 6: Run the full backend suite**

```bash
poetry run pytest -q && poetry run ruff check app workers tests
```
Expected: all pass, "All checks passed!".

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/work_log_service.py backend/tests/test_work_log_global.py
git commit -m "feat(review-queue): cross-client suggested work-log queries"
```

---

### Task 2: Schema + global read router

**Files:**
- Modify: `backend/app/schemas/work_log.py`
- Create: `backend/app/api/v1/work_log_global.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_work_log_global.py` (append)

**Interfaces:**
- Consumes: `work_log_service.suggested_across_clients(db)`, `work_log_service.suggested_count(db)` from Task 1.
- Produces: `GET /api/v1/work-log/suggested` → `list[WorkLogSuggestionOut]`; `GET /api/v1/work-log/suggested/count` → `{"count": int}`. Task 3 calls both.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_work_log_global.py`:

```python
def test_route_returns_suggestions_with_client_identity(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db, "Acme Dental")
    work_log_service.suggest(c.id, "technical", "Verified llms.txt", "r:1", db)

    r = client.get("/api/v1/work-log/suggested", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["client_id"] == str(c.id)
    assert body[0]["client_name"] == "Acme Dental"
    assert body[0]["category_label"] == "Technical"
    assert body[0]["description"] == "Verified llms.txt"
    assert body[0]["status"] == "suggested"


def test_route_excludes_non_suggested(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    pub = work_log_service.suggest(c.id, "content", "Published", "r:2", db)
    work_log_service.update_entry(pub, {"status": "published"}, db)

    r = client.get("/api/v1/work-log/suggested", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_count_route(client, db, auth_headers):
    from app.services import work_log_service
    c = _make_client(db)
    work_log_service.suggest(c.id, "technical", "One", "r:1", db)
    work_log_service.suggest(c.id, "content", "Two", "r:2", db)

    r = client.get("/api/v1/work-log/suggested/count", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"count": 2}


def test_routes_require_auth(client, db):
    assert client.get("/api/v1/work-log/suggested").status_code == 401
    assert client.get("/api/v1/work-log/suggested/count").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_work_log_global.py -q
```
Expected: the four new tests FAIL with 404 (route not registered).

- [ ] **Step 3: Add the schema**

Append to `backend/app/schemas/work_log.py`:

```python
class WorkLogSuggestionOut(WorkLogEntryOut):
    """A suggestion plus the client it belongs to, for the cross-client queue.

    Extends WorkLogEntryOut rather than redefining the shared fields — two
    independent models describing one row is how Phase 4 shipped a field with
    two different values.

    `client_name` defaults to "" and is assigned after model_validate, exactly
    as `category_label` already is: neither exists on the WorkLogEntry ORM
    object, so validation would fail if they were required.
    """
    client_id: uuid.UUID
    client_name: str = ""
```

`client_id` needs no default — it is a real column on `WorkLogEntry` and populates from the ORM object automatically.

- [ ] **Step 4: Create the router**

Create `backend/app/api/v1/work_log_global.py`:

```python
"""Cross-client work-log reads (spec §3.3).

READ ONLY by design. Publish/dismiss go through
PATCH /clients/{client_id}/work-log/{entry_id}, which already verifies the entry
belongs to the client in the URL. Adding a second write path here would mean a
second copy of that check, free to drift from the first.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import WORK_LOG_CATEGORY_LABELS
from app.core.database import get_db
from app.schemas.work_log import WorkLogSuggestionOut
from app.services import work_log_service

router = APIRouter(prefix="/work-log", tags=["work-log-global"])


@router.get(
    "/suggested",
    response_model=list[WorkLogSuggestionOut],
    dependencies=[Depends(require_api_key)],
)
def list_suggested(db: Session = Depends(get_db)):
    out: list[WorkLogSuggestionOut] = []
    for entry, client in work_log_service.suggested_across_clients(db):
        data = WorkLogSuggestionOut.model_validate(entry)
        data.category_label = WORK_LOG_CATEGORY_LABELS.get(
            entry.category, entry.category.title()
        )
        data.client_name = client.name
        out.append(data)
    return out


@router.get("/suggested/count", dependencies=[Depends(require_api_key)])
def count_suggested(db: Session = Depends(get_db)) -> dict[str, int]:
    return {"count": work_log_service.suggested_count(db)}
```

- [ ] **Step 5: Register the router**

In `backend/app/api/v1/router.py`, add `work_log_global` to the end of the import list on line 2, then add the include after the existing `work_log` line:

```python
router.include_router(work_log_global.router)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
poetry run pytest tests/test_work_log_global.py -q
```
Expected: 9 passed.

- [ ] **Step 7: Run the full backend suite**

```bash
poetry run pytest -q && poetry run ruff check app workers tests
```
Expected: all pass, "All checks passed!".

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/work_log.py backend/app/api/v1/work_log_global.py backend/app/api/v1/router.py backend/tests/test_work_log_global.py
git commit -m "feat(review-queue): global suggested + count read routes"
```

---

### Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: the two routes from Task 2.
- Produces: `WorkLogSuggestion` type; `getSuggestedWorkLog(): Promise<WorkLogSuggestion[]>`; `getSuggestedWorkLogCount(): Promise<number>`. Tasks 5 and 6 use these.

- [ ] **Step 1: Add the type**

In `frontend/src/types/index.ts`, immediately after the existing `WorkLogEntry` interface (which ends with `published_at: string | null`), add:

```typescript
// A suggestion in the cross-client Review Queue — WorkLogEntry plus the client
// it belongs to (see WorkLogSuggestionOut in backend/app/schemas/work_log.py).
export interface WorkLogSuggestion extends WorkLogEntry {
  client_id: string
  client_name: string
}
```

- [ ] **Step 2: Add the API functions**

In `frontend/src/lib/api.ts`, in the `// ── Work log ──` section, after the existing `patchWorkLogEntry` function, add:

```typescript
export async function getSuggestedWorkLog(): Promise<WorkLogSuggestion[]> {
  return apiFetch<WorkLogSuggestion[]>("/api/v1/work-log/suggested")
}

export async function getSuggestedWorkLogCount(): Promise<number> {
  const res = await apiFetch<{ count: number }>("/api/v1/work-log/suggested/count")
  return res.count
}
```

Add `WorkLogSuggestion` to the existing `@/types` import list at the top of `api.ts`.

- [ ] **Step 3: Typecheck**

Stop the dev server first if running. From `frontend/`:
```bash
npm run typecheck
```
Expected: no output (clean).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(review-queue): WorkLogSuggestion type + api client"
```

---

### Task 4: Route group restructure

Pure move + redirect. **No new behaviour** — every existing URL must still resolve identically. Doing this before the new page means the page lands in its final location once.

**Why:** the sidebar *and* the second auth layer both live in `src/app/clients/layout.tsx`. Next.js layouts apply only to their own subtree, so a top-level `/review-queue` would render with no sidebar and, more seriously, **no auth guard** — the layout's own comment says admin pages must fail closed. A `(admin)` route group gives global pages that layout. Parentheses mean the segment is invisible in URLs.

**Files:**
- Move: `frontend/src/app/clients/` → `frontend/src/app/(admin)/clients/`
- Move: `frontend/src/app/(admin)/clients/layout.tsx` → `frontend/src/app/(admin)/layout.tsx`
- Move: `frontend/src/app/(admin)/clients/gap-matrix/` → `frontend/src/app/(admin)/gap-matrix/`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/next.config.ts`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Move the tree**

From `frontend/`:
```bash
mkdir -p "src/app/(admin)"
git mv src/app/clients "src/app/(admin)/clients"
git mv "src/app/(admin)/clients/layout.tsx" "src/app/(admin)/layout.tsx"
git mv "src/app/(admin)/clients/gap-matrix" "src/app/(admin)/gap-matrix"
```

- [ ] **Step 2: Confirm the relative import still resolves**

`(admin)/layout.tsx` line 2 is `import { auth } from "../../../auth"`. `src/app/(admin)/` sits at the **same depth** as the old `src/app/clients/`, so this path is still correct and must NOT be changed. Confirm:

```bash
grep -n '\.\./\.\./\.\./auth' "src/app/(admin)/layout.tsx"
ls ../frontend/auth.ts 2>/dev/null || ls auth.ts
```
Expected: the import line prints, and `auth.ts` exists at the frontend root.

- [ ] **Step 3: Add the redirect**

In `frontend/next.config.ts`, add a `redirects()` alongside the existing `headers()`, inside `nextConfig`:

```typescript
  async redirects() {
    return [
      // Gap Matrix moved to the top level when global pages got their own
      // route group; keep old bookmarks working.
      { source: "/clients/gap-matrix", destination: "/gap-matrix", permanent: true },
    ]
  },
```

⚠️ `next.config.ts` already carries an unrelated uncommitted `output: "standalone"` line from the Docker/VPS work. Stage this file deliberately — do not sweep that line into this commit if it is still meant to be separate. Check with `git diff frontend/next.config.ts` before staging.

- [ ] **Step 4: Update the Sidebar's gap-matrix link and drop the reserved-route guard**

In `frontend/src/components/layout/Sidebar.tsx`, inside `NavLinks`, the current code reads:

```typescript
  // Static sibling routes under /clients that are NOT a client id — they must not
  // trigger the per-client nav block (otherwise it renders links like
  // /clients/gap-matrix/scan).
  const RESERVED_CLIENT_ROUTES = new Set(["gap-matrix"])
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const rawClientId = clientMatch?.[1]
  const clientId = rawClientId && !RESERVED_CLIENT_ROUTES.has(rawClientId) ? rawClientId : undefined
```

Replace with — the guard existed only because gap-matrix lived under `/clients/`, which is no longer true:

```typescript
  const clientMatch = pathname.match(/^\/clients\/([^/]+)/)
  const clientId = clientMatch?.[1]
```

Then update the gap-matrix active check and link. Current:

```typescript
  const gapActive = pathname === "/clients/gap-matrix"
```
becomes:
```typescript
  const gapActive = pathname === "/gap-matrix"
```

and in the JSX, `<Link href="/clients/gap-matrix" ...>` becomes `<Link href="/gap-matrix" ...>`.

- [ ] **Step 5: Update CLAUDE.md §9**

In the "Admin Panel Navigation" table in `CLAUDE.md`, change the gap-matrix line and add the new page. The block currently starts:

```
/                        → redirect to /clients
/clients                 → all clients overview
/clients/gap-matrix      → cross-client competitor gap matrix
```

Replace those three lines with:

```
/                        → redirect to /clients
/clients                 → all clients overview
/gap-matrix              → cross-client competitor gap matrix
/review-queue            → cross-client work-log inbox (pending suggestions)
```

And add this note directly under the route list:

```
Global (non-client-scoped) admin pages live at the TOP LEVEL, inside the
`src/app/(admin)/` route group so they share the sidebar + auth layout.
`/clients/*` means client-scoped. A route group's parentheses do not appear in
the URL. `/clients/gap-matrix` permanently redirects to `/gap-matrix`.
```

- [ ] **Step 6: Verify every existing URL still resolves**

Stop the dev server, then from `frontend/`:
```bash
npm run typecheck && npm run build
```
Expected: build succeeds and the route table lists `/clients`, `/clients/[id]`, `/clients/[id]/scan` … plus `/gap-matrix`. Confirm `/clients/gap-matrix` is **absent** from the route list (it is now a redirect, not a route).

- [ ] **Step 7: Commit**

```bash
git add "frontend/src/app/(admin)" frontend/src/components/layout/Sidebar.tsx frontend/next.config.ts CLAUDE.md
git commit -m "refactor(admin): (admin) route group so global pages share the auth layout

Sidebar and the second auth layer both lived in clients/layout.tsx, so a
top-level page would render with no sidebar and no auth guard. Route group
gives global pages that layout without changing any URL. Gap Matrix moves to
/gap-matrix with a permanent redirect from the old path."
```

---

### Task 5: Review Queue page

**Files:**
- Create: `frontend/src/app/(admin)/review-queue/page.tsx`
- Create: `frontend/src/app/(admin)/review-queue/ReviewQueueClient.tsx`
- Create: `frontend/src/app/(admin)/review-queue/actions.ts`

**Interfaces:**
- Consumes: `getSuggestedWorkLog()` (Task 3), `patchWorkLogEntry(clientId, entryId, patch)` (existing in `api.ts`).
- Produces: the `/review-queue` page. Task 6 links to it.

- [ ] **Step 1: Create the server actions**

Create `frontend/src/app/(admin)/review-queue/actions.ts`:

```typescript
"use server"

import { revalidatePath } from "next/cache"
import { patchWorkLogEntry } from "@/lib/api"
import type { WorkLogEntry, WorkLogStatus } from "@/types"

// Publish/dismiss reuse the per-client PATCH — the only write path into this
// table. Revalidate both the queue and the client's own activity page, since
// the entry appears on both.
export async function reviewWorkLogAction(
  clientId: string,
  entryId: string,
  patch: { description?: string; status?: WorkLogStatus },
): Promise<WorkLogEntry> {
  const entry = await patchWorkLogEntry(clientId, entryId, patch)
  revalidatePath("/review-queue")
  revalidatePath(`/clients/${clientId}/activity`)
  return entry
}
```

- [ ] **Step 2: Create the page (server component)**

Create `frontend/src/app/(admin)/review-queue/page.tsx`:

```typescript
import { getSuggestedWorkLog } from "@/lib/api"
import { ReviewQueueClient } from "./ReviewQueueClient"

export default async function ReviewQueuePage() {
  const suggestions = await getSuggestedWorkLog()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Review Queue</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Work we logged automatically, waiting for your review. Nothing here is
          visible to a client until you publish it.
        </p>
      </div>
      <ReviewQueueClient initialSuggestions={suggestions} />
    </div>
  )
}
```

- [ ] **Step 3: Create the client component**

Create `frontend/src/app/(admin)/review-queue/ReviewQueueClient.tsx`:

```typescript
"use client"

import { useState } from "react"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import type { WorkLogSuggestion } from "@/types"
import { reviewWorkLogAction } from "./actions"

export function ReviewQueueClient({
  initialSuggestions,
}: { initialSuggestions: WorkLogSuggestion[] }) {
  const [items, setItems] = useState(initialSuggestions)
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(initialSuggestions.map((s) => [s.id, s.description])),
  )
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function review(item: WorkLogSuggestion, status: "published" | "dismissed") {
    setPendingId(item.id)
    setError(null)
    try {
      const description = drafts[item.id]?.trim()
      // Only send the description when it actually changed — an unnecessary
      // write would re-sanitize and re-touch the row for nothing.
      const patch =
        status === "published" && description && description !== item.description
          ? { description, status }
          : { status }
      await reviewWorkLogAction(item.client_id, item.id, patch)
      setItems((prev) => prev.filter((i) => i.id !== item.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update that entry.")
    } finally {
      setPendingId(null)
    }
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="font-display text-lg font-semibold">Nothing waiting for review</p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            New work shows up here automatically as you deliver it.
          </p>
        </CardContent>
      </Card>
    )
  }

  // Preserve backend ordering (client name, then newest first) while grouping.
  const groups: { clientId: string; clientName: string; items: WorkLogSuggestion[] }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (last && last.clientId === item.client_id) last.items.push(item)
    else groups.push({ clientId: item.client_id, clientName: item.client_name, items: [item] })
  }

  return (
    <div className="space-y-5">
      {error && (
        <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      )}
      {groups.map((group) => (
        <Card key={group.clientId}>
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
            <CardTitle className="text-base">
              <Link href={`/clients/${group.clientId}`} className="hover:underline">
                {group.clientName}
              </Link>
            </CardTitle>
            <Badge variant="secondary">{group.items.length} waiting</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {group.items.map((item) => (
              <div
                key={item.id}
                className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center"
              >
                <Badge variant="outline" className="w-fit shrink-0">
                  {item.category_label}
                </Badge>
                <Input
                  value={drafts[item.id] ?? ""}
                  onChange={(e) =>
                    setDrafts((prev) => ({ ...prev, [item.id]: e.target.value }))
                  }
                  className="flex-1"
                  aria-label={`What we did for ${group.clientName}`}
                />
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(item.entry_date + "T00:00:00").toLocaleDateString("en-MY", {
                    day: "numeric",
                    month: "short",
                  })}
                </span>
                <div className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    disabled={pendingId === item.id}
                    onClick={() => review(item, "published")}
                  >
                    Publish
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={pendingId === item.id}
                    onClick={() => review(item, "dismissed")}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
```

Note the date parse: `item.entry_date + "T00:00:00"` forces local-midnight rather than UTC-midnight, so a 1st-of-month entry cannot render as the previous day on a UTC-negative host. (The public progress page has this bug; do not copy it.)

- [ ] **Step 4: Typecheck and build**

Stop the dev server, then from `frontend/`:
```bash
npm run typecheck && npm run build
```
Expected: clean; route table now lists `/review-queue`.

- [ ] **Step 5: Commit**

```bash
git add "frontend/src/app/(admin)/review-queue"
git commit -m "feat(review-queue): cross-client inbox page with inline edit"
```

---

### Task 6: Sidebar nav entry + count badge

**Files:**
- Modify: `frontend/src/app/(admin)/layout.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: `getSuggestedWorkLogCount()` (Task 3), the `/review-queue` page (Task 5).
- Produces: nothing downstream.

- [ ] **Step 1: Fetch the count in the layout**

`Sidebar` is a client component; the layout is a server component, so the count is fetched there and passed down. In `frontend/src/app/(admin)/layout.tsx`, add the import and the guarded fetch:

```typescript
import { getSuggestedWorkLogCount } from "@/lib/api"
```

Inside the component, after the existing auth check:

```typescript
  // Best-effort: this layout wraps every admin page, so a failing count must
  // never take the sidebar (and with it the whole panel) down. No badge is a
  // fine degradation; a crash is not.
  let suggestedCount = 0
  try {
    suggestedCount = await getSuggestedWorkLogCount()
  } catch {
    suggestedCount = 0
  }
```

Then pass it to both sidebars:

```typescript
      <Sidebar suggestedCount={suggestedCount} />
```
```typescript
        <MobileSidebar suggestedCount={suggestedCount} />
```

- [ ] **Step 2: Thread the prop through Sidebar**

In `frontend/src/components/layout/Sidebar.tsx`:

Add `Inbox` to the existing `lucide-react` import list.

Change the `NavLinks` signature to accept the count:

```typescript
function NavLinks({
  onNavigate, suggestedCount = 0,
}: { onNavigate?: () => void; suggestedCount?: number }) {
```

Add the nav entry directly after the Gap Matrix `<Link>`:

```typescript
      <Link href="/review-queue" onClick={onNavigate} className={linkClass(reviewActive)}>
        {activeBar(reviewActive)}
        <Inbox className={cn("h-4 w-4 shrink-0", reviewActive ? "text-primary" : "")} />
        Review Queue
        {suggestedCount > 0 && (
          <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-primary-foreground">
            {suggestedCount}
          </span>
        )}
      </Link>
```

and define its active flag next to the existing `gapActive`:

```typescript
  const reviewActive = pathname === "/review-queue"
```

Finally, both `Sidebar` and `MobileSidebar` must accept `suggestedCount` and forward it to `NavLinks`. Read their current signatures and add `{ suggestedCount }: { suggestedCount?: number }`, passing it through to every `<NavLinks />` call site — there are two (desktop and mobile sheet).

- [ ] **Step 3: Typecheck and build**

Stop the dev server, then from `frontend/`:
```bash
npm run typecheck && npm run build
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/app/(admin)/layout.tsx" frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(review-queue): sidebar entry + pending count badge"
```

---

### Task 7: Definition-of-done gate + walkthrough

**Files:** none (verification only).

- [ ] **Step 1: Run the seenby-verify gate**

Invoke the `seenby-verify` skill. From `backend/`:
```bash
poetry run pytest -q
poetry run ruff check app workers tests
```
Stop the dev server, then from `frontend/`:
```bash
npm run typecheck && npm run build
```
Confirm `poetry run alembic heads` still shows exactly one head, `de87b61a859c` — this plan adds no migration, so a second head means something was created by mistake.

Banned-language scan across changed files:
```bash
git diff --name-only HEAD~6..HEAD -- '*.py' '*.ts' '*.tsx' | while read f; do [ -f "$f" ] && grep -Hni -E "\b(cited|uncited|mentioned)\b|citation rate|ranking position|visibility gap|confidence score|char offset|token count|first mentioned" "$f"; done
```
Expected: no hits outside negative instructions in prompt files and the banned-word lists inside tests.

- [ ] **Step 2: Walkthrough**

Start the app (`run-app` skill), log in, then:

1. Visit `/review-queue` with nothing pending — confirm the empty state reads as success, not an error.
2. Fire a hook on a throwaway client (set an authority asset to live, or verify a toolkit file). Reload `/review-queue` — the suggestion appears under that client's name, and the sidebar badge shows a count.
3. Edit the wording in the inline field, click **Publish**. The row disappears; the badge decrements.
4. Open that client's `/clients/[id]/activity` — the entry is in **Published** with the edited wording, confirming the edit persisted through the shared PATCH.
5. Open the client's share link `/view/<token>/progress` — the published entry appears with the edited wording.
6. Fire another hook, click **Dismiss** — the row disappears and the entry shows as Dismissed on the activity page, never on the share link.
7. Visit `/clients/gap-matrix` — confirm it redirects to `/gap-matrix` and the page renders with the sidebar.
8. Confirm every client sub-page still works after the route-group move: `/clients`, a client overview, and at least two client sub-tabs.

⚠️ Browser-pane note: Radix checkboxes and Selects ignore synthetic clicks while the Browser pane is hidden (no compositing). Use `scroll_to` before clicking, or drive mutations through the admin API.

- [ ] **Step 3: Clean up walkthrough data**

Delete any work-log rows created during the walkthrough, scoped by `client_id` to the throwaway client. Note `ActivityLog`'s table is `activity_log` (singular) while the others are plural.

- [ ] **Step 4: Finish the branch**

Invoke `superpowers:finishing-a-development-branch` and follow the user's choice.

---

## Self-Review

**Spec coverage:**
- §3.1 service, status filtered at query, archived excluded, stable ordering → Task 1, all four behaviours have a test. ✓
- §3.2 `WorkLogSuggestionOut` extends `WorkLogEntryOut`, `category_label` set post-validate → Task 2 Step 3. The spec wrote `client_name: str`; the plan gives it a `""` default because `model_validate` on a `WorkLogEntry` cannot populate it — same reason `category_label` has one. Documented in the docstring. ✓
- §3.3 two admin-only read routes, writes stay on the per-client PATCH, router named `work_log_global.py` → Task 2. ✓
- §4.1 page grouped by client, inline editable description, publish/dismiss, empty state, `api.ts` only → Task 5. ✓
- §4.2 `GLOBAL_NAV` with badge, badge never breaks sidebar → Task 6 (the guard is in the layout, which is where the fetch happens). ✓
- §4.3 gap-matrix move + `next.config.ts` redirect + CLAUDE.md §9 → Task 4. ✓
- §5 error handling: count failure → no badge (Task 6 Step 1); queue failure → error state (Task 5 Step 3 renders `error`); stale row idempotent (no code needed — `update_entry` only assigns on change); sanitising already covered. ✓
- §6 all six backend tests → Tasks 1 and 2. Frontend typecheck/build/banned-scan → Task 7. ✓
- §7 no bulk publish — Global Constraints repeats the prohibition; the page has no multi-select. ✓
- §8 build order followed, with the route-group restructure inserted as Task 4 (a discovery made after the spec was written — the spec assumed top-level routing was a naming choice, but the auth layout made it structural). ✓

**Placeholder scan:** No TBD/TODO/"similar to Task N"/"handle errors appropriately". Two steps deliberately instruct the implementer to *read* current code rather than guess: Task 6 Step 2's `Sidebar`/`MobileSidebar` signatures (the plan states exactly what to add and that there are two `NavLinks` call sites, but not their current prop lists) and Task 4 Step 3's `git diff` check on `next.config.ts`. Both name precisely what to look for.

**Type consistency:** `suggested_across_clients(db) -> list[tuple[WorkLogEntry, Client]]` — defined Task 1, consumed Task 2 as `for entry, client in ...` (tuple order matches). `suggested_count(db) -> int` — Task 1, consumed Task 2. `WorkLogSuggestionOut` fields `client_id` + `client_name` map to the TS `WorkLogSuggestion extends WorkLogEntry` in Task 3 (`client_id: string` since JSON serialises UUID to string). `getSuggestedWorkLog` / `getSuggestedWorkLogCount` — Task 3, consumed Tasks 5 and 6. `reviewWorkLogAction(clientId, entryId, patch)` — Task 5 Step 1, called Task 5 Step 3 with the same argument order. `suggestedCount` prop name identical across layout, `Sidebar`, `MobileSidebar`, `NavLinks`.

**One risk the implementer should not silently resolve:** Task 4 moves 48 files. If `npm run build` after Step 6 shows any route missing from the table that existed before, stop and investigate rather than proceeding to Task 5 — a silently dropped route is the failure mode of a route-group move, and it will not surface as a type error.
