# Citation Provenance + Share-of-Source — Design (v1)

**Date:** 2026-07-03
**Status:** Approved for planning
**Scope:** v1 — admin-only, Perplexity-only, real citations only

## 1. Summary

SeenBy today answers *"are you seen by AI?"* — the same question every competitor
in the category answers. This feature answers the harder, more valuable one:
**"*why* did the AI recommend a competitor instead of you, and what specific thing
do you change to flip it?"**

When a Perplexity scan query is answered, Perplexity returns the sources it leaned
on. We currently discard them. This feature captures those citations, determines
which brands actually appear on each source, and rolls them up per client into:

- **Share of Source** — of the third-party sources AI trusts to answer your
  category's questions, what % feature you vs. each competitor.
- **Acquisition list** — the ranked set of specific third-party pages AI cites
  where a competitor appears and you do not.
- **Flip targets** — the top 3 sources most worth earning a mention on.

This turns a vague visibility gap into a concrete, ranked "go get mentioned here"
list — the deliverable that justifies an ongoing retainer.

## 2. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Attribution scope | **Real citations only** | No LLM-inferred attribution. Highest trust, zero hallucinated sources. |
| Platform coverage | **Perplexity-only** | Uses citations we already pay for. Zero cost change, zero risk to existing visibility scoring. |
| Presence depth | **Fetch + deterministic brand-match (Approach B)** | The ranked "who's on the page you're absent from" list is the actual killer insight. |
| Surfacing | **Admin page first** | Validate data quality on real scans before any client sees it. Client view + PDF are v1.1. |
| Storage | **Normalized `scan_query_source` table** | Purge-proof structured data, aggregated at read time (same pattern as `compute_competitor_intelligence`). |

## 3. Non-goals (v1)

- No inferred sources (no LLM attribution pass).
- No platform beyond Perplexity.
- No client view (`/view/[token]/*`) or PDF report section — that is v1.1.
- No historical backfill — provenance exists for scans from ship date forward only.

## 4. Data capture — the plumbing fix

`PlatformResult` (`app/services/platform_clients/base.py`) currently carries only
`text`, `model`, `input_tokens`, `output_tokens`. Perplexity's response includes a
sources array that is dropped at `perplexity.py:42`.

**Change:**
- Add `citations: tuple[SourceCitation, ...] = ()` to the frozen `PlatformResult`
  dataclass, defaulted empty so ChatGPT / Gemini / Claude clients are unaffected.
- `SourceCitation` is a small frozen dataclass: `url: str`, `title: str | None`,
  `rank: int` (1-based position in the source list).
- `PerplexityClient.query` reads `payload["search_results"]` (newer shape:
  `[{title, url, date}, …]`) with fallback to `payload["citations"]` (older shape:
  `[url, …]`). Missing/empty → `()`. This is the **only** platform-client change.

## 5. Storage — `scan_query_source`

One new table. One row per (client query result × cited source × rank). Structured
and purge-proof: it survives the 90-day raw-response purge exactly like
`brand_detected`, because it never stores raw response text.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `scan_query_result_id` | UUID FK → `scan_query_results.id` | `ON DELETE CASCADE` |
| `url` | Text | Full cited URL |
| `domain` | String, indexed | Normalized host (strip `www.`, lowercase) — aggregation key |
| `title` | String, nullable | From `search_results` when present |
| `rank` | Integer | 1-based position in the source list |
| `source_type` | String | `client_owned` \| `competitor_owned` \| `third_party` \| `null` (pre-enrichment) |
| `fetch_status` | String | `pending` \| `ok` \| `blocked` \| `error` |
| `present_brands` | JSONB, nullable | `{"client": bool, "competitors": [competitor_id, …]}` |
| `created_at` | timestamp | |

**Why sources come only from client-owned query rows** (`competitor_id IS NULL`):
those queries are "the questions buyers ask AI about your category." Their
citations are the sources AI trusts to answer them — precisely the population we
want Share-of-Source computed over. Competitor-owned query rows
(`competitor_id` set) are excluded in v1.

Presence is stored denormalized on each occurrence row (cheap; avoids a join at
read time). The same URL cited by N queries yields N rows, but is fetched and
brand-matched **once** per scan via an in-scan cache, and the same
`present_brands` value is written to each occurrence.

**Migration:** one Alembic migration creating `scan_query_source` (per CLAUDE.md
§10 — no raw `ALTER TABLE`). `PlatformResult` changes are code-only.

## 6. Scan integration — capture inline, enrich post-commit

Two phases, to keep the scan fast and isolate risky external I/O.

### 6a. Inline capture (during scan, fast, no network beyond the query itself)

In `_run_platform_queries` (`scan_service.py`), for **Perplexity** client-query
results, build `scan_query_source` rows from `result.citations` (URL + normalized
domain + title + rank), `source_type=NULL`, `fetch_status='pending'`,
`present_brands=NULL`. These are returned alongside the `ScanQueryResult` rows and
persisted in the same commit as the scan results (association is by the parent
`ScanQueryResult`, so rows are wired up when the parents get their IDs on flush).

`_run_platform_queries` gains a third return value (or an attribute carried on each
result) mapping each client `ScanQueryResult` to its captured source rows.

### 6b. Post-commit enrichment (best-effort, isolated)

New `provenance_service.enrich_scan_sources(scan_id, db)`, invoked in `run_scan`
immediately after the scan commit — **same isolation contract as the existing
alert / action-center / remediation post-commit steps** (CLAUDE.md §10):
`try` → on failure `db.rollback()` and swallow. A failed enrichment **never** marks
the scan failed.

Enrichment steps:
1. Load the client + competitors; build a domain → owner map from their `website`
   fields (normalized host match, including subdomains).
2. For each unique captured source URL in this scan:
   - Classify domain: client site → `client_owned`; a competitor site →
     `competitor_owned`; else → `third_party`.
   - `client_owned` / `competitor_owned`: no fetch needed; `fetch_status='ok'`,
     `present_brands` reflects the owner.
   - `third_party`: fetch the page through the **existing SSRF-guarded crawler**
     (`content_crawler.py` / `verification_crawler.py`), concurrent
     (`ThreadPoolExecutor`), hard per-fetch timeout, **de-duped by URL via an
     in-scan cache** so each URL is fetched at most once. Run `detect_brand_mention`
     for the client and each competitor against the fetched text.
     `fetch_status='ok'`, `present_brands` = who matched.
   - Blocked / errored fetch → `fetch_status='blocked'|'error'`, `present_brands`
     stays null (fail-open — the source contributes no presence data, same
     graceful-degradation spirit as an unavailable platform).
3. Write `source_type`, `fetch_status`, `present_brands` back to every occurrence
   row of that URL. Commit.

Bounds: a max-URLs-per-scan cap and per-fetch timeout keep wall-time bounded.
Because scans are on-demand background work, added latency is operationally
invisible.

*Deferred option:* if enrichment wall-time ever becomes a problem, promote it to a
queued Celery task in `content_tasks.py` — a small refactor, since it is already an
isolated service function taking `(scan_id, db)`.

## 7. Read model — `compute_share_of_source(client_id, db)`

New function in `provenance_service.py`. From the **latest completed scan**:

1. Pull `scan_query_source` rows joined to their `ScanQueryResult` where
   `competitor_id IS NULL` (client queries only).
2. Split by `source_type`. Self-citation (`client_owned` / `competitor_owned`) is
   reported separately from the third-party Share-of-Source math.
3. Over unique `third_party` URLs with `fetch_status='ok'`:
   - **Share of Source:** denominator = count of unique third-party source URLs;
     per-brand numerator = count of those URLs where the brand appears in
     `present_brands`. Yields client share % and each competitor's share %
     (shares can overlap — a page can feature multiple brands).
   - **Acquisition list:** unique third-party URLs where the client is absent and
     ≥1 competitor is present, ranked by **citation frequency** (number of
     occurrence rows across the scan's queries). Each entry: domain, title,
     citation count, and the competitors present.
   - **Flip targets:** the top 3 acquisition-list entries by citation frequency.
4. Return a whitelisted Pydantic schema (`ShareOfSourceResponse`). Never returns
   raw response text or fetched page bodies.

Edge cases returned gracefully: no completed scan; scan predates the feature (no
source rows); no competitors; all fetches failed (empty Share-of-Source with a
"no source data yet" state).

## 8. API + admin surface

- **Endpoint:** `GET /api/v1/clients/{id}/provenance` (admin, existing auth) →
  `ShareOfSourceResponse`. Route in `app/api/v1/`, logic in the service (CLAUDE.md
  §10 — no logic in routes).
- **UI:** a **new section on the existing `/clients/[id]/competitors` page** —
  a Share-of-Source bar and the acquisition-list table. No new route ⇒ **no
  CLAUDE.md §9 navigation change required.** All API access via `src/lib/api.ts`;
  types in `src/types/index.ts`; shadcn/ui only.

## 9. Language + review discipline

v1 is admin-only, so admin copy may be technical (`sources`, `citations` are fine
in the admin panel). For the v1.1 client view, the client-safe labels are
pre-named here so the schema/UI can carry them forward without churn:

- "Share of Source" → **"Sources AI trusts in your category"**
- per-brand → **"Seen on X of Y sources"** (never "cited" / "citation rate")
- acquisition list → **"Where your competitors are winning attention"**

Presence is deterministic, but the admin still reviews the acquisition list before
it informs any client deliverable — same admin-gated spirit as Brand Authority /
Content Quality.

## 10. Testing

**Unit — pure logic (no network):**
- Citation parsing: `search_results` shape, legacy `citations` shape, empty,
  missing key, malformed entry.
- Domain normalization + classification: `www`/subdomain handling; client vs.
  competitor vs. third-party; a competitor whose site is a subpath.
- Share-of-Source math: URL dedup; overlapping presence; no competitors; empty
  scan; all-third-party-failed.
- Acquisition ranking + flip-target selection (ties, <3 entries).

**Enrichment:**
- SSRF guard rejects internal / private URLs (reuse crawler's guard; assert it is
  invoked).
- Blocked / errored fetch → `fetch_status` set, `present_brands` null, no crash.
- In-scan cache: a URL cited by multiple queries is fetched exactly once.
- **Isolation:** an enrichment exception leaves the scan `completed` and does not
  raise out of `run_scan` (mirrors existing alert best-effort tests).

## 11. Files touched (anticipated)

- `app/services/platform_clients/base.py` — `PlatformResult.citations`, `SourceCitation`.
- `app/services/platform_clients/perplexity.py` — parse `search_results`/`citations`.
- `app/models/scan_query_source.py` — new model.
- `alembic/versions/*` — new migration.
- `app/services/scan_service.py` — inline capture + post-commit `enrich_scan_sources` call.
- `app/services/provenance_service.py` — new: `enrich_scan_sources`, `compute_share_of_source`.
- `app/schemas/provenance.py` — new: `ShareOfSourceResponse` and children.
- `app/api/v1/clients.py` (or new `provenance.py`) + `router.py` — new endpoint.
- `src/lib/api.ts`, `src/types/index.ts`, competitors page component — admin UI section.
- Tests under the backend test suite.
