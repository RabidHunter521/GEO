# SeenBy Premium Upgrade — Phase 2: Competitive Intelligence v2

## Context

Phase 1 (multi-platform scanning) shipped: scans run on ChatGPT/Perplexity/Gemini/Claude, `ScanQueryResult` rows carry `platform`, and `GeoScore.platform_breakdown` stores per-platform visibility. Phase 2 is the next step of the approved intelligence-first roadmap: turn the scan data SeenBy already collects into competitive insight a premium GEO agency can act on and show clients.

**Approved scope (user decisions locked):**
1. **Win/loss query analysis** — admin only. Pure post-processing of stored scan responses, no new AI calls.
2. **Claude content briefs** — on-demand button per lost query (cost control), persisted, admin only.
3. **Competitor visibility trends** — computed from historical `ScanQueryResult` rows (no snapshot table; `brand_detected` flags persist even after future response purges). Shown on admin competitors page AND client share view.
4. **Per-platform overtake alerts** — enrich the existing one-email-per-competitor alert with platform detail. No new emails.
5. **Industry benchmarking** — percentile vs other SeenBy clients in the same industry, min 3 scored clients, anonymous. Shown on admin client detail AND client share view overview.

**Key facts verified during exploration:**
- The 90-day response purge is not implemented yet; win/loss reads only the latest scan's `response_text`, trends use only `brand_detected` flags → both purge-safe by design.
- `scan_query_results.scan_id` has **no index** — add one in this phase's migration.
- `backend/tests/conftest.py:7` imports models explicitly for `create_all` — the new model must be added there.
- Latest Alembic head: `f6a7b8c9d0e1`.

---

## Step 1 — Migration + ContentBrief model

**New** `backend/app/models/content_brief.py`:
```python
class ContentBrief(Base):
    __tablename__ = "content_briefs"
    id: UUID pk
    client_id: UUID FK clients.id CASCADE, index=True
    scan_query_result_id: UUID FK scan_query_results.id CASCADE, unique=True  # one brief per query result; regenerate = upsert
    platform: String(50)
    query_text: Text            # denormalized for display
    competitors_seen: JSON      # list[str] of competitor names seen in that answer
    title: String(500)
    angle: Text
    outline: JSON               # list[str] of H2-level bullets
    generated_at: datetime default utcnow
```

**New migration** `backend/alembic/versions/a7b8c9d0e1f2_create_content_briefs_table.py` (`down_revision = 'f6a7b8c9d0e1'`): create table + `op.create_index('ix_scan_query_results_scan_id', 'scan_query_results', ['scan_id'])`.

**Modify** [conftest.py](backend/tests/conftest.py): add `content_brief` to the model import line.

## Step 2 — Win/loss service (no AI calls)

**New** `backend/app/services/win_loss_service.py` → `compute_win_loss(client_id, db) -> WinLossResponse`:
1. Latest completed scan (same query pattern as [competitor_intelligence_service.py](backend/app/services/competitor_intelligence_service.py)). None → empty response.
2. Fetch client's own results for that scan, filtered to `category.in_(WIN_LOSS_CATEGORIES)` and `hallucination_flagged IS FALSE`. **`WIN_LOSS_CATEGORIES = ("recommendation", "local")`** in `core/constants.py` — comparison queries name the competitor (always "seen" → poisoned signal) and brand queries name the client; only neutral-intent categories are fair.
3. Per result: `competitors_seen = [c.name for c in competitors if detect_brand_mention(r.response_text, c.name)]` (reuse [brand_detection.py](backend/app/services/brand_detection.py); `response_text is None` → empty).
4. Outcome per entry: `lost` (≥1 competitor seen, client not), `won` (client seen, none seen), `shared` (both), `open` (nobody).
5. Attach existing `ContentBrief` rows via one `scan_query_result_id.in_(...)` query.

**Schemas** (add to [competitor.py](backend/app/schemas/competitor.py)): `ContentBriefResponse` (id, title, angle, outline, competitors_seen, generated_at), `WinLossEntry` (result_id, platform, category, query_text, client_seen, competitors_seen, outcome, brief), `WinLossResponse` (scan_id, last_scan_at, summary counts dict, entries).

**Route** in [competitors.py](backend/app/api/v1/competitors.py): `GET /clients/{client_id}/competitors/win-loss`. Never exposed on client_view.

## Step 3 — Content brief service + endpoint

**New** `backend/app/services/content_brief_service.py` following the [action_center_service.py](backend/app/services/action_center_service.py) pattern (`anthropic_client()`, Haiku model from [claude_client.py](backend/app/services/claude_client.py), `strip_code_fences`, `json.loads` in try/except → `None` on failure):

`generate_brief_for_result(client, result, competitors_seen, db) -> ContentBrief | None`
- Prompt: GEO content strategist persona; business context (name/industry/city/description/audience); "When AI assistants were asked '{query}' on {platform label}, the answer included {competitors} but {client} was not yet seen by AI"; ask for JSON `{"title", "angle", "outline": [...]}` — publish-ready title, 1–2 sentence angle, 4–7 outline bullets. Prompt forbids "citation/mentioned/ranking position/visibility gap" so briefs are paste-safe for client deliverables. `max_tokens=1024`.
- Upsert on `scan_query_result_id` (regenerate updates fields + `generated_at`). Add `ActivityLog(event_type="brief_generated")`. Commit.

**Route**: `POST /clients/{client_id}/competitors/win-loss/{result_id}/brief` → `ContentBriefResponse`:
- 404 if result not found / not this client's scan / `competitor_id` not None; 422 if category outside `WIN_LOSS_CATEGORIES`; restrict to entries where client is **not seen** (lost + open).
- Recompute `competitors_seen` server-side (no request body trusted). Synchronous Claude call (~2–5s, matches toolkit-generate pattern). `None` → 502 "Brief generation failed — try again".

## Step 4 — Competitor visibility trends

**Add to** [competitor_intelligence_service.py](backend/app/services/competitor_intelligence_service.py): `compute_competitor_trends(client_id, db, limit=12)`:
1. Last 12 completed scans (id + completed_at), reversed oldest→newest (the GeoScore-history pattern from [client_view.py](backend/app/api/v1/client_view.py)).
2. One GROUP BY aggregate over those scan ids: `func.count()` + `func.sum(case(brand_detected))` grouped by `(scan_id, competitor_id)` — ≤72 grouped rows, fast with the new index.
3. Emit aligned series; a point is `None` when a competitor has no rows in that scan (added later). Overall visibility only (not per-platform) to keep the chart readable.

**Admin schemas**: `TrendScanPoint`, `TrendSeries` (competitor_id|None, name, points list[float|None]), `CompetitorTrendsResponse` (scans, client series, competitor series). **Route**: `GET /clients/{client_id}/competitors/trends`.

**Client view**: new `GET /view/{token}/competitors/trends` in [client_view.py](backend/app/api/v1/client_view.py) + whitelist schemas in [client_view.py schemas](backend/app/schemas/client_view.py): `ClientViewTrendSeries` (name, is_you, points), `ClientViewCompetitorTrends` (checked_at dates, series) — **dates only, no scan/internal ids**.

## Step 5 — Per-platform overtake alert enrichment

**Modify** [competitor_intelligence_service.py](backend/app/services/competitor_intelligence_service.py): promote `_visibility_by_platform` → public `visibility_by_platform` (update internal call sites).

**Modify** [alert_service.py](backend/app/services/alert_service.py) `check_competitor_overtake_alert` (lines 55–96):
- Trigger condition **unchanged** (overall citability exceeds client's) → same email volume, max one per competitor per scan. Per-platform-only leads do not fire (comment this).
- Compute per-platform visibility for client (once) and each overtaking competitor; `winning_platforms = [(platform, comp%, client%)]` where competitor is ahead.
- `_build_overtake_email` gains a "Platforms where {name} is ahead" section (`PLATFORM_LABELS` rows, omitted when empty). ActivityLog note appends "Ahead on: ChatGPT, Gemini." when non-empty.

## Step 6 — Industry benchmarking

**New** `backend/app/services/benchmark_service.py`:
- `compute_percentile(scores_by_client, client_id)` — pure math, unit-testable: `rank = 1 + count(score strictly > mine)`, `top_percent = ceil(rank / total * 100)`. Rank-based so the best of 5 reads "top 20%" (never "top 0%"); ties share the better rank.
- `compute_industry_benchmark(client, db) -> IndustryBenchmarkResponse | None` — latest-GeoScore-per-client subquery (mirror the pattern in [clients.py](backend/app/api/v1/clients.py) GET /clients), peers filtered by `archived_at IS NULL` and case/trim-insensitive industry match. Return `None` when `< MIN_BENCHMARK_PEERS (= 3)` scored peers incl. this client, or client has no score.

**Schemas**: new `backend/app/schemas/benchmark.py` — admin `IndustryBenchmarkResponse` (industry, peer_count, client_score, industry_average, rank, top_percent); client-view `ClientViewBenchmark` in client_view schemas (industry, peer_count, industry_average, top_percent — **no rank**).

**Routes**: admin `GET /clients/{client_id}/benchmark` in clients.py. Client view: add optional `benchmark: ClientViewBenchmark | None = None` to `ClientViewOverview` and populate in `get_overview` (additive, non-breaking, no extra fetch).

## Step 7 — Frontend

**Types** ([index.ts](frontend/src/types/index.ts)): `WinLossOutcome`, `ContentBrief`, `WinLossEntry`, `WinLossResponse`, `TrendSeries`, `CompetitorTrendsResponse`, `IndustryBenchmark`, `ClientViewCompetitorTrends`, `ClientViewBenchmark`; extend `ClientViewOverview` with `benchmark`.

**API** ([api.ts](frontend/src/lib/api.ts)): `getWinLoss`, `generateContentBrief(clientId, resultId)`, `getCompetitorTrends`, `getIndustryBenchmark`. ([view-api.ts](frontend/src/lib/view-api.ts)): `getViewCompetitorTrends(token)`.

**New** `frontend/src/components/competitors/VisibilityTrendChart.tsx` — multi-series inline-SVG line chart (same no-lib philosophy as [ScoreHistoryChart.tsx](frontend/src/components/view/ScoreHistoryChart.tsx)): polyline + dots per series, null points break segments, `is_you` series in primary color/thicker, muted competitors, legend, date labels when ≤8 points, `<title>` tooltips. Returns null with <2 points. Copy: "visibility frequency".

**New** `frontend/src/components/competitors/WinLossSection.tsx` (`"use client"`): summary chips (Won / "Your competitors are winning here (n)" / Shared / Open), entries with platform pill + query + "Seen by AI / Not yet seen by AI" + competitor names; lost/open entries get "Generate content brief" button (`useTransition` → server action, pending spinner, inline error); existing brief renders inline (title, angle, outline, generated date, Regenerate).

**New** `frontend/src/app/clients/[id]/competitors/actions.ts`: `generateBriefAction(clientId, resultId)` → `generateContentBrief` + `revalidatePath`.

**New** `frontend/src/components/IndustryBenchmarkCard.tsx` (server component): "You rank in the top {X}% of {industry} businesses tracked by SeenBy" + "Industry average: {avg} · based on {n} businesses"; admin variant adds rank + score. Renders nothing when null.

**Modify**:
- [clients/[id]/competitors/page.tsx](frontend/src/app/clients/[id]/competitors/page.tsx): parallel-fetch intelligence + win-loss + trends; trend chart after client summary card; win/loss section after it.
- [clients/[id]/page.tsx](frontend/src/app/clients/[id]/page.tsx): add `getIndustryBenchmark` to parallel fetches; benchmark card near score breakdown.
- [view/[token]/competitors/page.tsx](frontend/src/app/view/[token]/competitors/page.tsx): trend chart ("Your visibility frequency over time") between summary card and winning callout. No win/loss, no briefs.
- [view/[token]/page.tsx](frontend/src/app/view/[token]/page.tsx): benchmark card from `overview.benchmark`.

## Step 8 — Tests

New: `test_win_loss_service.py` (SQLite `db` fixture: classification outcomes, category restriction, hallucination + None-response exclusion, brief attachment, no-scan case), `test_content_brief_service.py` (patch `anthropic_client` per test_claude_action.py pattern: valid JSON persists, fenced JSON handled, malformed → None + nothing persisted, upsert no duplicate), `test_benchmark_service.py` (percentile math incl. ties/ceil; <3 peers → None; archived excluded; case-insensitive industry; client unscored → None).

Update: `test_alert_service.py` (per-platform lines in email, one email per competitor, no email on platform-only lead, note text), `test_competitor_intelligence.py` (trends ordering/cap/None alignment/math), `test_api_competitors.py` (win-loss 200/404, brief 404 for foreign result, trends shape).

## Verification

1. `alembic upgrade head` clean (content_briefs table + scan_id index); downgrade/re-upgrade works.
2. `pytest` green in backend/ (`.venv\Scripts\python.exe -m pytest -q`).
3. `npx tsc --noEmit` green in frontend/.
4. Manual e2e: scan a client with competitors → competitors page shows trend chart (≥2 scans) + win/loss counts; generate brief on a lost query → renders, survives reload, regenerate bumps `generated_at`, activity log shows `brief_generated`.
5. Share view: trends chart on `/view/[token]/competitors`; benchmark card on overview only when ≥3 industry peers; curl both new view payloads — no scan ids, result ids, response_text, or internal fields.
6. Overtake email contains the per-platform "ahead" section; still one email per competitor.
7. Language audit: `grep -ri "cited|mentioned|citation rate|visibility gap|ranking position"` over new/changed client-facing files → zero hits.

## Risks (accepted)

- Substring brand detection can false-positive generic competitor names → consistent with existing client detection; word-boundary improvement deferred.
- Free-form industry strings split benchmark cohorts; case/trim normalization mitigates — benchmark quality depends on picking from the fixed INDUSTRIES list.
- Synchronous Claude call in brief route (2–5s) — matches toolkit pattern; button shows pending state, 502 is retryable.

---

## Roadmap (unchanged guardrails)

- **Phase 3 — Agency operations:** portfolio dashboard at top of `/clients` (score deltas, needs-attention queue), bulk scan trigger (reuse ClientsManager multi-select), client filtering by score band/industry/location/last-scan.
- **Phase 4 — Premium experience + integrations:** Claude "what changed this month" narratives in PDF + share view, 90-day content roadmap generator (feeds on Phase 2 lost-query data), Slack/Telegram admin alerts, GA4 auto-pull into AiTrafficSnapshot.

**Still NOT in scope any phase (CLAUDE.md §11):** client dashboard login, self-serve signup/billing, white-label/reseller, multi-locale prompts, scheduled scans, webhooks, automated Brand Authority/Content Quality scoring.
