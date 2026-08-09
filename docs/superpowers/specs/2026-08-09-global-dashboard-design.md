# Global Dashboard — Design Spec

**Date:** 2026-08-09
**Status:** Approved in brainstorming, pending implementation plan
**Decided with:** Faris

## Purpose

The admin panel has no cross-client, time-ordered view of what happened. The
global nav answers "who are my clients" (/clients), "where are competitors
winning" (/gap-matrix), "how do cohorts compare" (/benchmarks), and "what's
waiting for my decision" (/review-queue) — but not **"what happened?"** Today
that requires visiting each client's /activity page one at a time.

The Dashboard is a global, read-only, filterable view of everything happening
across the agency: an event feed as the spine, with a summary stats strip
above it. It becomes the app's landing page.

## Decisions made (with rationale)

| Decision | Choice | Why |
|---|---|---|
| Spine of the page | Event feed, with stats strip above | For a one-admin agency where retention is the bottleneck, "something needs attention" beats KPI wallpaper |
| Stats strip content | Attention flags + portfolio health + LLM cost | What Faris checks every morning; cost exists nowhere in the UI today |
| Filter scope | Filters drive the **entire page** (tiles + feed) | Scoped tiles ("Client X cost $14 and dropped 6 pts this month") are insight; a fixed global average is wallpaper. Defaults: all clients, last 30 days |
| Noise handling | Three severity tiers + "Attention only" toggle | Flat feed buries the 4 rows that matter under hundreds of routine ones; burst-collapsing is fiddly and fights the date filter |
| Score-drop attention threshold | ≥5 points | Matches the existing ±5 weekly-digest threshold |
| Row links | Route by event type (static map), read-only page | Zero schema change, works retroactively for all existing rows, lands within one scroll of the target. No inline actions |
| Nav placement | First item; `/` redirects to `/dashboard`; logo links there | Landing on "what changed" is the reason to build it. One-line change to reverse |

## Data sources — all existing, no new collection

- **Feed:** `activity_log` only (client_id, event_type, note, created_at).
  Every meaningful action already writes here (~30 event types: scan_completed,
  scan_failed, report_sent, digest_sent, alert_sent, hallucination_flagged,
  toolkit_verified, assessment_accepted, deliverable_generated, citation_flip,
  share_link_revoked, client_created, …). No synthetic rows: score drops
  already fire `alert_sent`, and score movement lives in Tile 2.
- **Tile 2:** `geo_scores` (overall_score, computed_at per client).
- **Tile 3:** `llm_call_logs` (cost_usd, service, client_id, called_at).

## Filter contract

Three controls, held in **URL search params** (bookmarkable, refresh-safe,
lets the server component fetch):

- **Period:** Last 7 days / **Last 30 days (default)** / Last 90 days / Custom range
- **Client:** **All clients (default)** or one — reuse `searchable-select`
- **Event category:** All / Scans / Reports & Emails / Alerts & Issues /
  Content Work / Admin — plus an **"Attention only"** toggle that cuts across
  categories

One params model shared by both endpoints so filters genuinely drive the
whole page.

## Backend

New: `app/services/dashboard_service.py` (all logic) +
`app/api/v1/dashboard.py` (thin routes).

- `GET /api/v1/dashboard/summary` → the three tiles
- `GET /api/v1/dashboard/feed` → paginated events, 50/page ("Load more")

Separate endpoints so paginating the feed never recomputes the tiles.

**Tile 1 — Needs attention.** Period counts by kind: scans failed, platforms
unavailable, hallucinations flagged, alerts sent, share-of-source changes.
Each count links into the feed pre-filtered to that event type.

**Tile 2 — Portfolio health.** Average Growth Readiness across active
clients, average movement vs. period start, biggest gainer and biggest
decliner by name. Movement = each client's latest score in the window vs.
their last score before it; clients with no prior score contribute no delta.
Colors via `get_score_color()` / `getScoreColor()` — never hardcoded.

**Tile 3 — Cost.** Total `cost_usd` in period + top spending service; the
selected client's share when a client filter is active. `client_id` is
SET NULL on client delete, so orphaned rows **must still count** in the total
and surface as "Unattributed" — otherwise the tile under-reports.

**Admin-only by construction:** the cost tile must never reach a client
surface. The dashboard endpoints live with the admin API and must never be
reused by `/view/[token]` share-view code paths.

## Event classification — `app/core/constants.py`

Three maps keyed by event type, plus a `KNOWN_ACTIVITY_EVENT_TYPES` set:

- `EVENT_TIERS`: attention / notable / routine.
  Attention: scan_failed, scan_platform_unavailable, hallucination_flagged,
  alert_sent, citation_flip, scan_blocked_budget.
  Notable: report_sent, report_generated, toolkit_verified,
  assessment_accepted, deliverable_generated, client_created, and similar.
  Routine: scan_completed, digest_sent, traffic_updated, and similar.
  (Exact assignment of all ~30 types happens in the implementation plan.)
- `EVENT_CATEGORIES`: the five dropdown groups.
- `EVENT_LINK_ROUTES`: event type → client-scoped route
  (e.g. hallucination_flagged → `/clients/[id]/scan`,
  report_sent → `/clients/[id]/reports`).

**Unmapped types default to *notable*, not routine** — a future event type
must be visible, not silently swallowed. A coverage test asserts every type
in `KNOWN_ACTIVITY_EVENT_TYPES` has an entry in all three maps (same
rationale as `nav-icon-coverage.test.ts`, which exists because a missing map
entry crashed production twice).

## Frontend

- `(admin)/dashboard/page.tsx` — server component; reads `searchParams`,
  fetches via `src/lib/api.ts` (never direct fetch in components).
- `(admin)/dashboard/DashboardClient.tsx` — filter bar + feed interactivity.
- Types in `src/types/index.ts`. shadcn/ui only (`select`,
  `searchable-select`, `card`, `badge` all exist — no new primitives).
- Tier styling: attention rows get a colored left border + badge; notable a
  plain badge; routine muted text. Every row links to its mapped page.
- "Load more" button, not infinite scroll.

**Language rules (§2):** `citation_flip` displays as **"Share-of-source
change"**. Nothing on this page may say cited / uncited / citation rate /
mentioned. Confidence scores, char offsets, token counts never surface (the
cost tile shows dollars, not tokens — token counts stay internal).

## Sidebar & routing

- Add `/dashboard` first in `ADMIN_GLOBAL_NAV`; add a `GLOBAL_NAV_ICONS`
  entry. Icon must NOT be `LayoutDashboard` (already means per-client
  Overview) — use `Radar` or `Home`.
- `/` redirect: `/clients` → `/dashboard`. Logo href likewise.
- Amend CLAUDE.md §9: new page + changed redirect.

## Migration

`activity_log`'s only composite index leads with `client_id`
(`ix_activity_client_event_created`), which cannot serve the default
all-clients-by-time query. One Alembic migration adds `ix_activity_created_at`
on `activity_log (created_at DESC)`. No new table → no RLS clause, but the
full `seenby-migrations` runbook applies (revision chain, test bootstrap).

## Known trap: timezone mismatch

`activity_log.created_at` is **timezone-naive** (deliberately downgraded in
migration `0ef658851600`); `llm_call_logs.called_at` is **timezone-aware**.
One date filter hits both tables. The service must normalize the period
bounds explicitly per table — never let SQLAlchemy compare naive against
aware — or the cost tile and feed silently cover different windows at period
boundaries. Tests must cover this boundary.

## Out of scope (additive later if earned)

Live polling / auto-refresh, unread or "since last visit" markers, CSV
export, sparklines in tiles, collapsing routine bursts (option C), inline
actions from the feed, and any `link_path` / `entity_id` schema upgrade for
precise row links (option B — easy upgrade if route-by-type ever annoys).

## Testing

- Backend: coverage test for the three event maps; each filter combination;
  period boundaries under naive-vs-aware timezones; cost aggregation
  including orphaned (client_id NULL) rows; score deltas when a client has no
  prior score; pagination.
- Frontend: typecheck + build; `nav-icon-coverage.test.ts` must pass with the
  new entry.
- Banned-language scan; full `seenby-verify` gate before merge.
