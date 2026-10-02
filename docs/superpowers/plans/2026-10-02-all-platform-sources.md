# All-Platform Source Capture — Implementation Plan

> **For agentic workers:** follow `seenby-phase`. One commit per task, test-first,
> `seenby-verify` gates per diff. Invoke `seenby-migrations` for Task 5 and
> `seenby-client-output` for Tasks 8 and 11.

**Goal:** Record the sources ChatGPT, Claude and Gemini answers drew from, the
same way Perplexity's are recorded today, so Share-of-Source, the acquisition
list, flip detection, authority prioritisation, market intelligence and query
stability run on all four platforms instead of one.

**Why now:** all four platforms already run with web search / grounding and
already return their sources in the API response — we pay for them and throw
them away (`scan_service.py:175` gates capture on `platform == "perplexity"`).
No new API cost; roughly 4x the source data.

**Non-goals:** no score change (no SCORE_VERSION bump — sources never feed
Growth Readiness); no new client-facing page; no UI scraping of consumer apps.

## Grounded findings (verified against the code 2026-10-02)

1. **Capture gate** — `scan_service.py:175` only attaches `ScanQuerySource`
   rows for Perplexity. `PlatformResult.citations` already exists on the base
   dataclass; the ChatGPT, Claude and Gemini adapters never fill it.
2. **Tracked-query samples never capture sources on ANY platform**
   (`scan_service.py` sample loop, ~line 196–241). But
   `query_stability_service` uses `source_domains` as an agreement dimension
   (`_DIMENSIONS`, line ~149). Every sample therefore has `frozenset()` → the
   source dimension always agrees 100%. **Corrected 2026-10-02:** this does
   NOT inflate client-visible stability — `score` is the MINIMUM across
   dimensions, so a constant 1.0 can never raise it or change the state, and
   no frontend renders the per-dimension `agreement` breakdown. It is a
   meaningless entry in the API payload only. The real hazard is Task 6:
   once capture is on, legacy empty-set samples and new populated samples
   disagree and stability would DROP for no real reason. **Task 9 must ship
   in the same release as Task 6** — never deploy Task 6 alone.
3. **Trend discontinuity** — `share_of_source_snapshots` has no record of
   which platforms fed it. The first all-platform scan would produce a jump in
   the admin trend, the monthly PDF's sources section
   (`report_service._gather_sources_trend`) and the Phase 6 benchmark metric
   (`benchmark_snapshot_service._share_of_source`) that is really a coverage
   change, not a market change. Same class of bug the score versioning
   already guards against (`scoring_service.scores_comparable`).
4. **Enrichment cap is order-biased** — `provenance_service.enrich_scan_sources`
   fetches the first 60 third-party URLs in dict-insertion order
   (`_MAX_THIRD_PARTY_FETCHES = 60`); the rest stay `pending` forever and are
   silently excluded from share. With 4x the URLs, share would be computed on
   whichever platform's URLs happened to be inserted first.
5. **Gemini returns redirect URLs** — grounding chunks carry
   `https://vertexaisearch.cloud.google.com/grounding-api-redirect/...` with
   the real domain only in `web.title`. `normalize_domain(c.url)` would file
   every Gemini source under `vertexaisearch.cloud.google.com`.
6. **ChatGPT appends `?utm_source=openai`** to cited URLs, which would split
   one page into two URLs for dedupe and flip matching.
7. `url_safety.SafeResponse` has no final-URL field, so the redirect hop
   target can't be read after `safe_get` today.
8. Current Alembic head: `feef21ce8e5a`.

## Source semantics (decide once, document in methodology)

| Platform | What counts as a source | Field |
|---|---|---|
| Perplexity | unchanged — `search_results` (fallback `citations`) | existing |
| ChatGPT | URLs cited inline in the answer | `output[].content[].annotations[]` where `type == "url_citation"` |
| Claude | URLs cited inline in the answer | text blocks' `citations[]` where `type == "web_search_result_location"` |
| Gemini | grounding sources shown with the answer | `candidates[0].grounding_metadata.grounding_chunks[].web` |

Rank = 1-based order of first appearance; duplicates collapse to the first
rank. Verify every field path against the installed SDK version with Context7
before coding (openai `^2.0`, anthropic `^0.50`, google-genai `^1.0`). Every
parser is defensive: any exception → `()` and a structlog warning; a parsing
slip must never fail a query or a scan.

---

## Task 1 — URL canonicalisation + domain hint

**Files:** `platform_clients/base.py`, `provenance_service.py` (helper),
`tests/test_provenance_capture.py`

- Add `domain_hint: str | None = None` to `SourceCitation` (used only when the
  URL host is a known redirector).
- Add `canonical_source_url(url) -> str`: strip `utm_*` query params and the
  fragment; leave everything else (path, other params) intact.
- Add `GROUNDING_REDIRECT_HOSTS: Final = ("vertexaisearch.cloud.google.com",)`
  to `core/constants.py`.

**Done when:** tests cover utm stripping, fragment stripping, non-utm params
kept, unparseable input returned unchanged.

## Task 2 — ChatGPT citation parser

**Files:** `platform_clients/chatgpt.py`, `tests/test_platform_clients.py`

- `_parse_citations(response)` walks `response.output` message items →
  `content[]` → `annotations[]` of type `url_citation`; canonicalise; dedupe
  by canonical URL in order; title from the annotation.
- Return it as `PlatformResult.citations`.

**Done when:** tests with `SimpleNamespace` fakes cover: two citations in
order, duplicate collapsed, utm stripped, no annotations → `()`, malformed
object → `()` (no raise), existing usage/search-count tests still pass.

## Task 3 — Claude citation parser

**Files:** `platform_clients/claude.py`, `tests/test_platform_clients.py`

- `_parse_citations(response)` walks `response.content` text blocks →
  `block.citations` of type `web_search_result_location` (`url`, `title`);
  canonicalise; dedupe in order.
- Searched-but-not-cited results (`web_search_tool_result` blocks) are NOT
  counted, matching the ChatGPT "cited inline" semantics.

**Done when:** same test matrix as Task 2, plus a response that searched but
cited nothing → `()`.

## Task 4 — Gemini grounding parser

**Files:** `platform_clients/gemini.py`, `tests/test_platform_clients.py`

- `_parse_citations(response)` reads
  `response.candidates[0].grounding_metadata.grounding_chunks[].web`
  (`uri`, `title`). For redirect hosts, set `domain_hint` from
  `normalize_domain(title)` and keep `title=None` (Gemini's title is the
  domain, not a page title).
- Any missing link in the chain → `()`.

**Done when:** tests cover redirect URI + domain hint, a non-redirect URI,
no grounding metadata → `()`, malformed → `()`.

## Task 5 — Migration: capture flag + snapshot coverage

**Files:** `models/scan_query_result.py`, `models/share_of_source_snapshot.py`,
`core/constants.py`, new Alembic revision (down_revision `feef21ce8e5a`),
`tests/conftest.py` only if a model is added (none is).

- `scan_query_results.sources_captured: bool | None` (nullable, no default).
  NULL = legacy row whose capture state is unknown; True = adapter returned a
  parsed source list (possibly empty); False = adapter had no parser.
- `share_of_source_snapshots.source_capture_version: str | None` and
  `source_platforms: JSONB | None` (sorted list).
- Backfill existing snapshots to `source_capture_version = "v1"`,
  `source_platforms = ["perplexity"]` — deterministic: before this release
  only Perplexity was ever captured.
- `SOURCE_CAPTURE_VERSION: Final = "v2"` in constants.
- No new table → no RLS line needed; no `REVOKE ... FROM anon` (CLAUDE.md §8).

**Done when:** upgrade → downgrade → upgrade clean on SQLite tests and a
Postgres snapshot per `seenby-migrations`; `alembic heads` single.

## Task 6 — Capture on every platform, including tracked samples

**Files:** `scan_service.py`, `tests/test_provenance_capture.py`,
`tests/test_scan_service.py`

- Remove the `platform == "perplexity"` gate. Extract one helper
  `_attach_sources(sqr, result)` used by the main client-query loop AND the
  tracked-sample loop. Control queries and competitor-tracking queries stay
  uncaptured (unchanged behaviour).
- Domain = `normalize_domain(url)` unless the host is in
  `GROUNDING_REDIRECT_HOSTS`, then `domain_hint`; skip a citation whose final
  domain is empty.
- Set `sqr.sources_captured = True` for all four adapters now that each has a
  parser.

**Done when:** tests prove sources are attached for each of the 4 platforms,
for tracked samples, NOT for control/competitor rows, Gemini rows get the hinted
domain, and a platform returning `()` still yields `sources_captured=True` with
zero rows.

## Task 7 — Enrichment: resolve redirects, prioritise, cap honestly

**Files:** `url_safety.py`, `provenance_service.py`,
`tests/test_provenance_enrichment.py`

- Add `url: str` (final URL after redirects) to `SafeResponse`.
- Before classification, resolve redirector URLs through `safe_get` (each hop
  SSRF-checked as today); on success rewrite `row.url` (canonicalised) and
  `row.domain`; if the resolved domain disagrees with the hint, trust the
  resolved one and log it. On failure keep the hint domain, mark
  `fetch_status="error"`.
- Order third-party URLs by citation count (desc), then by how many platforms
  cited them, before applying the cap. Raise
  `_MAX_THIRD_PARTY_FETCHES` 60 → 150 (move to constants). Rows beyond the
  cap get `fetch_status="skipped"` instead of staying `pending` forever.
- Log `skipped` count in `scan_sources_enriched`.

**Done when:** tests cover redirect resolution, hint fallback on failure,
most-cited URLs fetched first, overflow marked `skipped`, owned-domain
classification unchanged. Measure enrichment wall time on the demo client
and record it in the ledger (must stay well inside the 25-min soft limit).

## Task 8 — Trend comparability (admin, PDF, benchmarks)

**Files:** `provenance_service.py`, `schemas/provenance.py`,
`report_service.py`, `benchmark_snapshot_service.py`, frontend
share-of-source trend component + `types/index.ts`, tests.

- `compute_and_persist_snapshot` writes `source_capture_version` and
  `source_platforms` (sorted distinct platforms of the scan's client-owned rows
  with `sources_captured is True`).
- `sources_comparable(a, b)`: same version AND same platform list.
- History endpoint: add `coverage_changed: bool` per point (vs the previous
  point); the admin chart draws a break / marker there instead of a line.
- PDF `_gather_sources_trend`: when the two latest snapshots aren't
  comparable, set `share_then=None`, suppress the "no longer missing" list,
  and render one client-safe line (via `seenby-client-output`):
  *"We now track the sources ChatGPT, Gemini and Claude draw from as well as
  Perplexity, so this month's figure starts a new baseline."*
- Benchmarks: `_share_of_source` uses only snapshots at the current
  `SOURCE_CAPTURE_VERSION`; older ones return None (excluded, not mixed).
- Flip detection: skip when the previous snapshot isn't comparable.

**Done when:** tests: v1→v2 pair → no delta, no flips, baseline line present;
v2→v2 same platforms → delta as today; platform toggled off between scans →
not comparable; benchmark ignores v1 rows. Banned-language scan passes
("sources AI answers drew from", never "cited").

## Task 9 — Stability: stop scoring sources that were never captured

**Files:** `query_stability_service.py`, `tests/test_query_stability_service.py`

- `QuerySample.source_domains` becomes `frozenset[str] | None`; None when the
  row's `sources_captured` is not True.
- The source-domain dimension is evaluated only when every compared sample
  has captured sources; otherwise it is omitted from `agreement` and from the
  score (not counted as agreeing).
- Release coupling: Task 6 and Task 9 deploy together (see finding 2).
  Client-visible stability scores should be unchanged by this pair; verify
  on the demo client before and after.

**Done when:** tests: legacy-only samples → no source dimension; mixed
legacy/new → no source dimension; all-captured → dimension present and
computed; pure brand/position dimensions unchanged.

## Task 10 — Per-platform view of sources (admin)

**Files:** `provenance_service.py`, `schemas/provenance.py`,
`api/v1/competitors.py`, frontend share-of-source card, `src/lib/api.ts`,
`src/types/index.ts`, tests.

- `ShareOfSourceResponse.by_platform`: for each platform, total unique
  third-party sources, the client's share, and its top 5 domains.
- Admin card gets a platform toggle (All / ChatGPT / Perplexity / Gemini /
  Claude). This is the "Gemini leans on Facebook and directories, ChatGPT on
  editorial sites" insight that drives which placements to chase.
- Admin-only for now; client view unchanged.

**Done when:** API test for a two-platform fixture; typecheck + build pass;
screenshot of the card on the demo client in the ledger.

## Task 11 — Docs + methodology

**Files:** `docs/methodology.md`, `docs/architecture.md`,
`provenance_service.py` module docstring, `methodology_service.py` if it
describes sources.

- Methodology gains a short "Sources" paragraph with the semantics table above
  in plain language, the v1 → v2 coverage change, and the limitation that API
  sources can differ from what a consumer app shows.
- Architecture map: "provenance capture — all enabled platforms".

## Task 12 — Verify + release

- Full `seenby-verify`.
- Release via `seenby-release` (migration against Railway Postgres, `alembic
  current == heads`).
- Post-release smoke: run one scan on the demo client; confirm source rows
  exist for every enabled platform, Gemini rows have real domains, a v2
  snapshot is written, the admin trend shows the coverage marker, and the next
  PDF preview shows the new-baseline line.
- Record: "verified locally" vs "verified on prod" separately.

## Risks

| Risk | Mitigation |
|---|---|
| SDK field paths differ from this plan | Context7 check before Tasks 2–4; defensive parsers return `()` |
| Gemini redirect links expire before enrichment | Enrichment runs minutes after the scan; hint domain survives failure |
| Enrichment time grows | Prioritised cap of 150, 8 workers, 10s timeout; measured in Task 7 |
| Clients see stability numbers change | Task 9 note; mention in the next monthly narrative if material |
| Trend jump misread as progress | Task 8 comparability guard on every consumer |
