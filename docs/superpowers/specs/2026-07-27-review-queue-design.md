# Review Queue — Cross-Client Work-Log Inbox — Design Spec

**Date:** 2026-07-27
**Status:** Approved design, pending implementation
**Context:** First global (non-client-scoped) admin surface. Phase 5 shipped auto-suggest
hooks that fire across every client, but the only way to find a `suggested` entry is to
open each client's activity page one at a time. This closes that gap.

## 1. Goal

Give the admin one place to review every pending work-log suggestion across all clients,
edit its wording, and publish or dismiss it.

The suggest/publish split exists so nothing reaches a client without an explicit human
decision. That guarantee is only as good as the admin's ability to *find* what is waiting.
With seven clients and no cross-client view, suggestions sit unreviewed — which means work
that was genuinely delivered never appears in the client's report or share link. The
retainer goes unproven for want of a list.

## 2. Non-goals

- **No new mutation path.** Publish/dismiss reuse the existing per-client PATCH route.
- **No "publish all" button.** See §7 — this is a deliberate omission, not an oversight.
- **No published/dismissed history.** Those stay on each client's activity card. This page
  is an inbox with an empty state, not a browser.
- **No polling.** The count is fetched with the page, not on a timer.
- **No changes to the suggest hooks, the work-log model, or any client-facing surface.**
  This is an admin-only read surface plus a page. No migration.
- **No score, dimension, or `SCORE_VERSION` change.**

## 3. Backend

### 3.1 Service — `app/services/work_log_service.py`

Two additions, both filtering `status == "suggested"` **at the query** and excluding
archived clients (matching the existing `_get_client_or_404` behaviour):

```
suggested_across_clients(db: Session) -> list[tuple[WorkLogEntry, Client]]
suggested_count(db: Session) -> int
```

`suggested_across_clients` joins `clients`, filters `Client.archived_at IS NULL`, and
orders by `Client.name` then `WorkLogEntry.entry_date DESC`, `created_at DESC` — stable
ordering so the page does not reshuffle between refreshes.

`suggested_count` uses `.count()`. It must **not** hydrate rows to compute a number; this
is the same lesson as `has_published()`, added when review found `has_work_log` loading a
client's entire published history to produce a boolean.

### 3.2 Schema — `app/schemas/work_log.py`

```
class WorkLogSuggestionOut(WorkLogEntryOut):
    client_id: uuid.UUID
    client_name: str
```

Extends the existing output rather than defining a parallel shape. Phase 4's worst bug came
from two independent code paths populating one response model and disagreeing on a field;
inheriting keeps a single definition of the shared fields.

`category_label` is set post-`model_validate` exactly as `_out()` already does in
`work_log.py` — the subclass inherits that requirement, so the new router must apply it too.

### 3.3 Routes — `app/api/v1/work_log_global.py` (new)

New router, prefix `/work-log`, registered in `router.py`. Both routes
`Depends(require_api_key)`:

| Route | Returns |
|---|---|
| `GET /work-log/suggested` | `list[WorkLogSuggestionOut]` |
| `GET /work-log/suggested/count` | `{"count": int}` |

Read-only. Writes continue through the existing
`PATCH /clients/{client_id}/work-log/{entry_id}`, which already 404s when the entry does
not belong to the client in the URL. Keeping that as the sole write path means the
ownership guard stays exercised by every caller and there is no second validation
implementation to drift.

**Router naming:** the existing per-client router is `work_log.py` with prefix
`/clients/{client_id}/work-log`. The new file is `work_log_global.py` to avoid two routers
in one module with different prefixes.

## 4. Frontend

### 4.1 Page — `src/app/review-queue/page.tsx` (new)

Sections grouped by client, each with the client name, a pending count, and a link to that
client's overview. Within a section, one row per suggestion:

- **Description** — editable text field, pre-filled with the suggested wording
- **Category** — chip, using `WORK_LOG_CATEGORY_LABELS`
- **Entry date** — formatted, not raw ISO
- **Publish** / **Dismiss** — buttons

Editing then publishing is two actions against the same row: PATCH the description if it
changed, then PATCH the status. The page refetches after either terminal action so the row
leaves the list.

**Empty state** is the success condition: "Nothing waiting for review." Calm, not an error,
not an empty table with headers.

All fetches go through `src/lib/api.ts` (CLAUDE.md §10 — no `fetch` in components). Types in
`src/types/index.ts`. shadcn/ui only.

### 4.2 Navigation — `src/components/layout/Sidebar.tsx`

A new `GLOBAL_NAV` array above the existing `CLIENT_NAV`:

| Label | Href | Icon |
|---|---|---|
| All Clients | `/clients` | `Users` |
| Gap Matrix | `/gap-matrix` | `Table2` |
| Review Queue | `/review-queue` | `Inbox` |

Review Queue shows a count badge when the count is non-zero. **The badge must never break
the sidebar**: a failed count request degrades to no badge, following the best-effort
pattern in CLAUDE.md §10. The sidebar renders on every admin page, so a throwing fetch
there takes down the whole panel.

### 4.3 Routing change

`/clients/gap-matrix` → `/gap-matrix`, establishing that global surfaces live at the top
level and `/clients/*` means client-scoped.

The old path keeps working via a permanent redirect declared in `next.config.ts`'s
`redirects()` (the file already exports `headers()`, so this follows the existing shape):
`{ source: "/clients/gap-matrix", destination: "/gap-matrix", permanent: true }`. A config
redirect rather than a placeholder page means the old route leaves the app router entirely
and cannot drift out of sync with the real page.

Note `next.config.ts` currently carries an uncommitted `output: "standalone"` addition for
the Docker/VPS work. The redirect change must be staged without sweeping that unrelated
line into this commit.

**CLAUDE.md §9 must be updated in the same commit** — it pins the exact admin nav structure
and forbids adding pages without amending it.

## 5. Error handling

- Count fetch failure → no badge, page still renders (§4.2).
- Queue fetch failure → error state on the page with a retry, not a blank section list.
- **Stale row** — if an entry was already published or dismissed in another tab, the PATCH
  still succeeds: `update_entry` only assigns when `new_status != entry.status`, so the
  transition is idempotent. The row simply disappears on refetch. No special handling.
- Banned language on the edit path needs no new logic: `update_entry` already routes
  descriptions through `sanitize_text`, as `suggest()` does at write time.

## 6. Testing

Backend:

1. Cross-client isolation — suggestions from two clients both appear, each carrying the
   correct `client_id` and `client_name`.
2. Only `suggested` appears — `published` and `dismissed` rows are absent.
3. Archived clients excluded — a suggestion belonging to an archived client does not appear
   and is not counted.
4. `suggested_count` equals `len(suggested_across_clients)` for the same fixture.
5. Both routes 401 without an API key.
6. Ordering is stable and grouped — all of one client's rows are contiguous.

Frontend: `tsc --noEmit`, `next build`, and the banned-language scan across changed files.

## 7. The rubber-stamping risk

Grouping by client and putting Publish buttons in a column makes clearing the list fast and
satisfying. That is the failure mode: the suggest/publish split exists precisely so
auto-generated wording gets human judgement before a client reads it, and a queue optimised
for speed invites publishing without reading.

Two decisions follow, and they should not be quietly reversed later:

- **Inline editing is mandatory, not optional.** The description is a text field, not static
  text with an edit affordance behind a click. Seeing the wording in an editable box is what
  prompts reading it.
- **No "publish all", no multi-select, no keyboard shortcut that publishes.** This will be
  the obvious next feature request the first time the queue has fifteen items in it. The
  correct response to a large queue is that the hooks are too chatty, not that publishing
  should be faster.

If a future change adds bulk publish, this section is the argument it needs to answer.

## 8. Build order

1. Service functions + tests (`suggested_across_clients`, `suggested_count`)
2. Schema + global router + route tests
3. `api.ts` client functions + types
4. Review Queue page
5. Sidebar `GLOBAL_NAV` + badge + gap-matrix move + redirect + CLAUDE.md §9
6. Verify gate (`seenby-verify`) + walkthrough
