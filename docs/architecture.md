# SeenBy — Architecture Map (one page)

Read this before exploring the code. It reflects the codebase as of 2026-07-06.
Rules and invariants live in CLAUDE.md — this file is only the map. The
client-facing definition, assumptions, and limitations of current measurement
are in [the methodology](methodology.md).

**Stack:** Next.js 15 (`frontend/`) · FastAPI (`backend/app/`) · PostgreSQL (Supabase in prod) via SQLAlchemy + Alembic · Celery + Redis (`backend/workers/`) · Cloudflare R2 (PDFs) · WeasyPrint · Claude/OpenAI/Gemini/Perplexity APIs.

## Request flow

```
Browser (admin, NextAuth login)
  → frontend/src/lib/api.ts            # ALL fetches go through here (bearer ADMIN_API_KEY, server-side)
  → backend/app/api/v1/<domain>.py     # thin routes; router.py registers them
  → backend/app/services/<domain>_service.py   # all business logic
  → backend/app/models/*.py            # one file per entity → Postgres
```

Public client view is the same pattern but unauthenticated:
`/view/[token]/*` → `api/v1/client_view.py` → whitelisted response schemas only (never raw AI responses / internal fields). Invalid/revoked token → uniform 404.

## The scan flow (the heart of the product)

```
POST via api/v1/scans.py
  → scan_service.run_scan
      query_builder            # builds up to 20 queries/platform (4 categories) + competitor tracking queries
      ThreadPoolExecutor       # one future per platform; per-future try/except — one platform failing never sinks the scan
      platform_clients/        # chatgpt, perplexity, gemini, claude API callers (circuit_breaker, budget_service, cost_tracker wrap calls)
      brand_detection          # deterministic regex "Seen by AI" — the core metric
      position_extraction      # Claude extracts list rank (additive, never replaces seen/not-seen)
      provenance capture       # Perplexity source provenance → scan_query_source rows
      scoring_service          # 5-dimension Growth Readiness (`overall_score`; weights in core/constants.py; SCORE_VERSION)
  → commit
  → post-commit, best-effort (catch + rollback + swallow, never undo the scan):
      alert_service            # score drop / overtake / hallucination → email + Telegram (SYNCHRONOUS — there is no alert_tasks)
      provenance_service.enrich_scan_sources   # SSRF-guarded fetch (url_safety) + brand matching on third-party sources
      action_center_service    # Claude drafts ≤5 actions; impact computed server-side, never by Claude
```

## Async work (Celery — thin tasks, logic stays in services)

| Task file (workers/tasks/) | Delegates to | Purpose |
|---|---|---|
| scan_tasks | scan_service | background scan runs |
| report_tasks | report_service → r2_service | monthly PDF: data → HTML → WeasyPrint → R2 → admin reviews → send |
| digest_tasks | digest_service | weekly email (Resend, contact@seenby.my); Claude action only on ±5pt move |
| content_tasks | content_analysis / content_brief / content_roadmap services | crawls + Claude generation |
| maintenance_tasks | retention_service | purge raw responses at 90d, archived clients at 6mo |

## Other load-bearing services

- `client_view.py` (25K) + `share_link_service` — the public surface; largest route file, treat with care.
- `report_service.py` (61K) — the entire monthly PDF; also `proof_card_service` (quote cards), `snippet_service`, `headline_battle_service`, `revenue_service` (pipeline RM math — returns nothing without an avg deal value).
- `win_loss_service` / `gap_matrix_service` / `competitor_intelligence_service` — head-to-head views (neutral categories only: recommendation + local).
- `assessment_service` / `benchmark_service` — assisted Brand Authority & Content Quality scoring (Claude suggests, admin gates).
- `toolkit_service` + `verification_crawler` — generates and live-verifies
  `robots.txt`, `schema.json`, and optional `llms.txt` / `llms-full.txt`.
  Technical Foundations currently reflects verified `robots.txt` AI-crawler
  access; verified structured data drives Structured Data. The optional llms
  files do not independently increase Growth Readiness.
- `provenance_service` / `causality_service` / `ga4_traffic_service` —
  source provenance enrichment, optimised-versus-control query comparisons,
  and recognised AI-referral traffic synchronisation from configured GA4.
- `misinformation_service` / `authority_service` / `citability_service` /
  `work_log_service` — administrator-reviewed factual-risk workflow,
  authority asset tracking, page citability audits, and the cross-client
  Review Queue.
- `language_sanitizer` — programmatic banned-language defense; the CLAUDE.md §2 table is law on every client-facing string.

## Frontend layout

`frontend/src/app/` — admin pages mirror the nav in CLAUDE.md §9 plus `/view/[token]/*`.
`src/components/` (shadcn/ui only) · `src/lib/api.ts` (all calls) · `src/lib/score-utils.ts` (band colors — mirror of backend constants) · `src/types/index.ts` (all types).

## Where to start for common changes

| You want to change… | Start at |
|---|---|
| how a score is computed | `services/scoring_service.py` + `core/constants.py` (bump SCORE_VERSION) |
| what a scan asks | `services/query_builder.py` + QUERY_TEMPLATES in constants |
| what the client sees | `api/v1/client_view.py` schemas + `frontend/src/app/view/` |
| the monthly PDF | `services/report_service.py` (+ report_tasks) |
| emails | `services/digest_service.py` / `alert_service.py` / `email_service.py` |
| a new entity | model file + Alembic migration + service + route, in that order |
