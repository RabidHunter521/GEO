# Phase 3 — Agency Operations

## Context

SeenBy is an agency-model platform: Faris manages many clients from one admin panel. Today `/clients` is a flat card grid — no portfolio-level view, scans must be triggered one client at a time, and there's no way to filter as the roster grows. Phase 3 adds: (1) a portfolio dashboard at the top of `/clients` (score deltas + needs-attention queue), (2) bulk scan trigger reusing the existing ClientsManager multi-select, (3) client filtering by score band / industry / location / last-scan recency.

**Key finding from exploration:** `GET /api/v1/clients` already returns `industry`, `city/state/country`, `latest_overall_score`, `last_scan_at` per client, with no pagination — so all filtering and portfolio math can be client-side. The only backend gaps are **previous score** (for deltas) and **latest scan status** (for "scan failed" detection), plus a scan-in-progress guard for bulk safety.

No DB schema change → **no Alembic migration needed**.

---

## Part A — Backend

### A1. Extend `ClientListItem` schema — `backend/app/schemas/client.py`

```python
class ClientListItem(ClientResponse):
    latest_overall_score: float | None = None
    last_scan_at: datetime | None = None
    previous_overall_score: float | None = None      # NEW
    latest_scan_status: str | None = None            # NEW: pending/running/completed/failed
    latest_scan_triggered_at: datetime | None = None # NEW: recency even when scan failed
```

### A2. New service `backend/app/services/client_list_service.py`

Move list-building logic out of the route (project convention: business logic in services). `backend/app/api/v1/clients.py:21-66` `list_clients` becomes a one-liner calling `build_client_list(db)`.

Query approach — **window functions** (replaces the current `max(computed_at)` subquery at clients.py:35-52):

```python
rn = func.row_number().over(
    partition_by=GeoScore.client_id,
    order_by=(desc(GeoScore.computed_at), desc(GeoScore.id)),  # id breaks ties
).label("rn")
# filter rn <= 2: rn==1 → latest score / last_scan_at; rn==2 → previous score
```

Same pattern (rn == 1) over `Scan` ordered by `desc(Scan.triggered_at)` → `latest_scan_status`, `latest_scan_triggered_at`. Both restricted with `.in_(client_ids)`. 3 queries total regardless of client count. `ROW_NUMBER` works on Postgres and the SQLite test fixture (≥3.25), and is the only clean way to get "second latest" without duplicate-row bugs on ties.

### A3. Scan-in-progress guard — `backend/app/services/scan_service.py` + `backend/app/api/v1/scans.py`

```python
ACTIVE_SCAN_STALE_MINUTES = 15  # in app/core/constants.py

def has_active_scan(client_id: uuid.UUID, db: Session) -> bool:
    """Pending/running Scan triggered within the stale window."""
```

In `POST /scans/` trigger endpoint: if `has_active_scan(...)` → `HTTPException(409, "Scan already in progress")`. The 15-min stale window prevents a crashed Celery worker from locking a client out forever (a full 4-platform scan takes ~2 min). This also protects the existing single-scan page from double-triggers — check `ScanClient.tsx` error handling surfaces it gracefully (show toast, don't crash).

---

## Part B — Frontend

### B1. Types — `frontend/src/types/index.ts`

Add the three new fields to `ClientListItem` (mirror A1, `string | null` for datetimes). No `api.ts` changes — fields flow through `getClients()`.

### B2. Pure-logic module `frontend/src/lib/client-list-utils.ts`

Keeps ClientsManager thin; reuses `getScoreBand` from `frontend/src/lib/score-utils.ts` (never re-hardcode band thresholds):

```ts
export function scoreDelta(c: ClientListItem): number | null  // latest − previous
export type AttentionReason = "score_drop" | "low_score" | "scan_failed" | "stale" | "never_scanned"
export function attentionReasons(c: ClientListItem, now: Date): AttentionReason[]
export interface ClientFilters { band; industry; country; recency: "all" | "7d" | "30d" | "never" }
export function applyFilters(clients: ClientListItem[], f: ClientFilters, now: Date): ClientListItem[]
```

Needs-attention criteria (named constants at top of file):
1. `score_drop`: delta ≤ −5 (matches the ±5 digest rule in project spec)
2. `low_score`: band name === "low"
3. `scan_failed`: `latest_scan_status === "failed"`
4. `never_scanned`: no score and no scan
5. `stale`: `last_scan_at` > 30 days old (matches monthly report cadence)

Recency filter uses `last_scan_at` (= last *successful* scan — failed scans don't refresh it; intentional).

### B3. New components in `frontend/src/components/clients/`

1. **`PortfolioSummary.tsx`** — stat-card row above the grid: total clients, portfolio average score (nulls excluded, band color via existing `ScoreBadge`/score-utils), improved/declined counts (delta > 0 / < 0), needs-attention count. Computed from the **full** list (does not react to filters).
2. **`NeedsAttentionQueue.tsx`** — compact card listing clients with ≥1 attention reason: name, score + delta arrow, reason `Badge`s ("Score dropped 8 pts", "Last scan failed", "No scan in 30+ days", "Never scanned"), each row links to `/clients/{id}`. Hidden when empty.
3. **`ClientFilterBar.tsx`** — shadcn `Select`s: Score band (All / each band / No score), Industry (unique values from data), Country (unique values / Not set), Last scan (Any / Last 7 days / Last 30 days / Never) + "Clear filters" ghost button + "{n} of {m} clients" count. Controlled: receives `filters` + `onChange`.

(Admin panel — internal terminology OK; match existing tone: "Last scan", "No scans yet".)

### B4. `frontend/src/components/clients/ClientsManager.tsx` changes

- Generalize `removeMode: boolean` → `selectionMode: "none" | "remove" | "scan"`; reuse `selected` set and `toggle/cancel` as-is.
- Toolbar: add "Scan clients" button (RefreshCw icon) next to "Remove client". In scan mode the confirm button reads "Scan (n)" with primary styling (not destructive). Pass `selectionVariant?: "destructive" | "primary"` to `ClientCard` for checkbox/highlight color — the only ClientCard change besides an optional delta arrow next to `ScoreBadge` (`+4` green / `−6` red, hidden when null).
- Scan confirm: `window.confirm` (matches remove pattern) → `await bulkScanAction(ids)` → sonner toast "Triggered N scans" + "M skipped — scan already running" when applicable → exit selection mode. No polling on the list page (per-client scan page already polls).
- Filtering: `const visible = useMemo(() => applyFilters(clients, filters), …)`; grid renders `visible`; `PortfolioSummary`/`NeedsAttentionQueue` render from full `clients`. Empty-filtered state: "No clients match these filters" + clear button (distinct from existing "No clients yet").

### B5. Server action — `frontend/src/app/clients/actions.ts`

```ts
export async function bulkScanAction(ids: string[]): Promise<{ triggered: number; skipped: number }> {
  // sequential loop over existing triggerScan(id); each POST returns 202 fast
  // apiFetch throws Error("API POST /api/v1/scans/ → 409") — message includes status,
  // so match /→ 409$/ to count "skipped"; rethrow-as-skipped for other errors is fine for MVP
  // then revalidatePath("/clients")
}
```

---

## Implementation order (each step shippable)

1. Backend: A1 schema → A2 service + route refactor → A3 guard → pytest.
2. Frontend types + `client-list-utils.ts`.
3. `bulkScanAction` + ClientsManager selection-mode generalization + ClientCard variant.
4. `ClientFilterBar` + filter wiring.
5. `PortfolioSummary` + `NeedsAttentionQueue`.

## Edge cases

- **0 scans**: all new fields null → no delta, excluded from average, "Never scanned".
- **1 scan**: previous null → delta null (never show "+72 from 0"); not counted improved/declined.
- **Failed-only scans**: no GeoScore rows → score null, `latest_scan_status="failed"` → flagged; `last_scan_at` stays null (correct).
- **Pending/running latest scan**: not an attention reason; optional subtle "Scanning…" hint on card.
- **`computed_at` ties**: handled by `desc(id)` tiebreaker in window order.
- **Archived clients**: already excluded at the endpoint.
- **Stale running scan** (worker crash): 15-min window in `has_active_scan` prevents permanent 409 lockout.

## Verification

Backend (`backend/tests/`, existing patterns in `conftest.py` / `test_api_clients.py`):
- New `test_client_list_service.py` with the real SQLite db fixture: clients with 0/1/2/3 GeoScores → correct latest/previous; failed Scan without GeoScore → `latest_scan_status="failed"`; archived excluded; tie resolved deterministically.
- Update `test_api_clients.py` for the route delegation + new field serialization.
- Scans: 409 when active scan exists; trigger allowed when the active scan is older than the stale window.
- Run: `cd backend && pytest` (full suite — 223 tests currently passing must stay green).

Frontend:
- `npm run build` / typecheck (catches `ClientListItem` changes everywhere).
- Manual: client with ≥2 scans shows delta; bulk-select 2 clients → scan → toast counts; immediately re-trigger → skipped count; each filter + combinations; empty-filter state; needs-attention rows link correctly.

## Risks / notes

- The 409 guard changes single-scan page behavior on double-trigger — handle the error in `ScanClient.tsx` with a friendly message (small addition in step 1/3).
- Needs-attention thresholds (drop ≥5, stale >30d) are product decisions encoded as named constants — easy to tune later. Per-client `score_drop_threshold` is deliberately left to the alert service; the queue uses the flat −5 delta for consistency with the digest rule.
- Portfolio summary intentionally ignores filters (truthful portfolio view); one-line change if preference differs.
