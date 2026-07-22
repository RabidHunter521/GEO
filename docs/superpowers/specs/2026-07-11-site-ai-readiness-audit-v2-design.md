# Site AI-Readiness Audit v2 + Toolkit Expansion — Design Spec

**Date:** 2026-07-11
**Status:** Approved design, pending implementation
**Phase:** 2 of the GEO end-to-end roadmap (Phase 1 = Share-of-Source trend, speced 2026-07-10)

## 1. Goal

Turn the three-signal toolkit verification (llms.txt / schema.json / robots.txt) into a
full website AI-readiness audit, and expand the toolkit generators, so SeenBy covers the
"Website AI Readiness Audit" and "Technical GEO" categories of a complete GEO agency:
crawlability, sitemap, metadata, headings, canonical, mobile, structured data, and
llms-full.txt — each with a pass/warn/fail verdict and a plain-English fix instruction
Faris can hand to the client.

## 2. Non-goals

- **No score formula change.** Technical Foundations and Structured Data keep their
  existing behavior (toolkit verification flips them; CLAUDE.md §6). The audit is
  informational and a client deliverable. Deriving dimension scores from audit results
  is a possible later change that would bump SCORE_VERSION — explicitly out of scope here.
- No multi-page site crawl. The audit fetches at most 4 URLs per run: homepage,
  robots.txt, sitemap.xml, llms.txt (+ llms-full.txt). Depth crawling is Phase 3
  territory (page-level citability) and stays out of this spec.
- No Lighthouse/Core Web Vitals integration. Response time is measured with a simple
  wall-clock on the homepage fetch; that is honest and cheap.
- No scheduled audits (MVP rule: on-demand only).

## 3. The audit — checks and verdicts

New service `backend/app/services/site_audit_service.py`. Every check returns:

```python
{"id": str, "label": str, "status": "pass" | "warn" | "fail" | "unknown",
 "detail": str,   # what we found, plain English
 "fix": str}      # what to do about it, plain English (empty when pass)
```

`unknown` is used when a fetch failed (timeout, blocked) — a crawl failure must never
crash the audit or masquerade as a client problem.

**Group A — AI crawl access** (extends what exists)
1. `robots_exists` — robots.txt returns 200.
2. `robots_ai_bots` — parse robots.txt properly (stdlib `urllib.robotparser` semantics,
   per-bot): each bot in `AI_CRAWLER_BOTS` may fetch `/`. Fail lists the blocked bots.
   This replaces the current naive `"gptbot" in text` substring check *for the audit
   only* — `verification_crawler.verify_robots_txt` keeps its behavior (it verifies
   the SeenBy-generated file, where the substring is guaranteed).
3. `llms_txt` — exists, non-empty (reuse `verification_crawler.verify_llms_txt`).
4. `llms_full_txt` — exists, non-empty. `warn` when missing (it's optional), never fail.
5. `https` — site serves HTTPS; http:// redirects to https://.

**Group B — Sitemap**
6. `sitemap_exists` — from robots.txt `Sitemap:` line, else `/sitemap.xml`. 200 + parses
   as XML (`<urlset>` or `<sitemapindex>`).
7. `sitemap_urls` — contains ≥ 1 `<loc>`. Detail reports the count.
8. `sitemap_fresh` — newest `<lastmod>` within 180 days → pass; older → warn; no
   lastmod at all → warn ("AI systems can't tell how fresh your content is").

**Group C — Homepage content signals** (single fetch, parsed with BeautifulSoup —
already a dependency via `ai_readiness_service`)
9.  `title` — present, 10–70 chars (warn outside range).
10. `meta_description` — present, 50–170 chars (warn outside range).
11. `canonical` — `<link rel="canonical">` present and same-domain.
12. `open_graph` — og:title + og:description present (og:image → detail note only).
13. `h1` — exactly one H1 (0 → fail, >1 → warn).
14. `heading_order` — no skipped levels in the first 20 headings (h2 before any h3, etc.);
    warn only.
15. `viewport` — `<meta name="viewport">` present (mobile-friendliness proxy).
16. `internal_links` — ≥ 10 same-domain `<a href>` on the homepage (warn below).
17. `response_time` — homepage TTLB < 2s pass, 2–5s warn, > 5s fail.

**Group D — Structured data**
18. `jsonld_present` — ≥ 1 `<script type="application/ld+json">` that parses as JSON.
19. `jsonld_types` — detail lists the `@type`s found; pass when Organization or
    LocalBusiness present, warn otherwise.

All fetches go through `url_safety.safe_get` / `is_safe_crawl_url` (SSRF guard),
timeout 10s, ThreadPoolExecutor fan-out like `ai_readiness_service` (Group A/B URLs in
parallel; Group C/D share the one homepage fetch).

**Summary line** computed server-side: `{passed: n, warned: n, failed: n, unknown: n}`.
No composite 0–100 audit score in this phase — a made-up number next to the real GEO
score invites confusion; counts are honest.

## 4. Persistence and trend

New model `backend/app/models/site_audit.py`:

```python
class SiteAudit(Base):
    __tablename__ = "site_audits"
    id            UUID pk
    client_id     UUID fk clients.id ondelete CASCADE, index
    checks        JSON  # full list of check dicts, exact shape above
    passed / warned / failed / unknown   Integer  # denormalized summary
    created_at    datetime
```

Alembic migration creates the table (RLS enabled in the same migration — lesson from
scan_query_sources). Every run inserts a new row; history is the point (Phase 5's
monthly report reads "latest vs previous within period" for the technical-delta
section). Retention: rows are small JSON, keep indefinitely; revisit if it ever matters.

Competitor audits are **live-only, not persisted** — same rule as
`ai_readiness_service` ("a competitor's readiness never feeds the client's score").

## 5. API

In `backend/app/api/v1/site_audit.py` (registered in router.py):

- `POST /api/v1/clients/{id}/site-audit` — run audit on the client's website, persist,
  return the row. Also writes `ActivityLog(event_type="site_audit_run", note=...)`.
- `GET /api/v1/clients/{id}/site-audit/latest` — latest row + delta vs previous run
  (`fixed: [check ids that went fail/warn → pass]`, `regressed: [...opposite...]`).
- `POST /api/v1/clients/{id}/site-audit/competitor/{competitor_id}` — live audit of a
  competitor site, same check list, not persisted, informational banner in response.

Admin-only (existing bearer auth). Client view gets nothing in this phase.

## 6. Toolkit expansion

**llms-full.txt generator.** New `generate_llms_full_txt(client)` in toolkit_service,
same pattern as `generate_llms_txt` but `max_tokens=4096` and an extended prompt
(services in detail, FAQ from client profile, policies, preferred URLs). New prompt
builder in `app/prompts/toolkit.py`.

**Schema expansion.** `build_schema_json` prompt gains two more types in the same
`@graph`: `Service` (one per main service, from client.description) and
`BreadcrumbList` (Home → Services). Existing types (LocalBusiness, Organization,
FAQPage) unchanged. Still one schema.json file — no per-page schema in this phase.

**Model change.** `ToolkitFiles` gains `llms_full_txt: Text nullable` and
`llms_full_verified: bool default False` (nullable because existing rows predate it;
UI shows "Generate" when null). Alembic migration.

**Verification.** `verification_crawler.verify_llms_full_txt(website)` (same shape as
`verify_llms_txt`); `verify_all` returns the new key. Toolkit page shows the fourth
file with the same copy + download + plain-English instructions treatment (CLAUDE.md §6).
llms-full.txt verification does **not** touch dimension scores — only the original
three files drive the score flip, unchanged.

## 7. Frontend

On `/clients/[id]/toolkit` (no new nav page — §9 untouched):

- New "Site AI-Readiness Audit" card below the generators: Run button →
  results grouped A–D with pass/warn/fail/unknown chips, detail + fix text per check,
  "last run <date>" line, and a "Since last audit: N fixed, N regressed" delta line
  when a previous run exists.
- Fourth file card for llms-full.txt (generate / copy / download / verify), matching
  the existing three.

On `/clients/[id]/competitors`: the existing AI-readiness checker section gains a
"Full audit" button per competitor that opens the same grouped-results view inline
(live data, "not saved" note). Reuses the same results component.

All fetches through `src/lib/api.ts`; types in `src/types/index.ts`; shadcn/ui only.

## 8. Language rules

Check labels/details/fixes are client-facing (they land in the Phase 5 report). They go
through the CLAUDE.md §2 table — no "crawl budget", "indexing" jargon without plain
English; never "cited/mentioned". All fix strings are literal constants in the service
(not Claude-generated), so `language_sanitizer` is not needed on this path — but the
banned-language grep in seenby-verify covers the file anyway.

## 9. Error handling

- Per-check try/except: any exception → `unknown` with detail "Could not check —
  the site didn't respond" style text. The audit always returns 19 checks.
- Homepage fetch failure poisons only Group C/D (all `unknown`), not A/B.
- SSRF: every URL through `is_safe_crawl_url`; unsafe → `unknown`, logged.
- Competitor audit failures return per-check `unknown`, HTTP 200 (matches
  ai_readiness_service philosophy: partial data beats an error page).

## 10. Testing

`backend/tests/test_site_audit_service.py` — mocked `safe_get` with HTML/XML fixtures:
1. Fully healthy fixture site → 19 passes.
2. robots.txt disallowing GPTBot + ClaudeBot → `robots_ai_bots` fail names both bots.
3. Missing sitemap, missing canonical, two H1s, no viewport → correct statuses + fixes.
4. Homepage timeout → Groups C/D all `unknown`, A/B unaffected.
5. Sitemap index (`<sitemapindex>`) parses; lastmod 300 days old → warn.
6. Delta computation: fail→pass shows in `fixed`, pass→fail in `regressed`.

`test_toolkit_service.py` additions: llms-full generation (mock Anthropic), schema
prompt includes Service + BreadcrumbList, verify_all returns 4 keys.
API tests: run + latest endpoints, activity log row written, competitor route not
persisting. Migration up/down. seenby-verify gate before merge.

## 11. Build order

1. Migration (site_audits table + toolkit_files columns, RLS on).
2. site_audit_service + tests.
3. toolkit_service llms-full + schema expansion + tests.
4. API routes + tests.
5. Frontend toolkit card + competitor button.
6. seenby-verify, then walkthrough on the running app (seenby-demo-check habits).
