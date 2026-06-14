# Backend Audit — SeenBy MVP

**Date:** 2026-06-14
**Scope:** `backend/app/` (FastAPI + SQLAlchemy/PostgreSQL) and `backend/workers/` (Celery/Redis). Read-only audit — no code changed.
**Codebase size:** ~6,545 LOC across 14 routes, 15 models, 30 services, 4 worker task modules, 18 Alembic migrations.

Severity legend: **Critical** (fix before more load) · **High** · **Medium** · **Low**.

> **Update 2026-06-14 (branch `backend-audit-fixes`):** the following are implemented.
> - **2.1** FK/hot-column indexes — migration `f1a2b3c4d5e6_add_performance_indexes`.
> - **2.2** 90-day raw-response purge + **2.3** 6-month post-churn delete — `app/services/retention_service.py`, `workers/tasks/maintenance_tasks.py` (daily Beat job 04:00 UTC), `CHURN_DELETE_DAYS` constant, `tests/test_retention_service.py` (4 tests).
> - **3.1** Per-call HTTP timeouts (90s) on every platform client, with SDK self-retries disabled so they don't stack with `query_with_retry`; Celery `task_soft_time_limit`/`task_time_limit` (25/30 min).
> - **3.5** Celery `result_expires` (24h).
> - **4.1** SVG logo uploads rejected (backend + frontend accept filter/help text).
> - **3.2** boto3 client cached (thread-safe singleton) with connect/read timeouts; the logo upload now offloads the blocking call via `run_in_threadpool` so it no longer stalls the event loop.
> - **1.1** Global exception handler — unhandled errors return a uniform `{"detail": ...}` 500 and are logged with request context (no leaked stack traces).
> - **1.2** Per-IP rate limiting on the public `/view/*` router (`app/core/rate_limit.py`, Redis-backed, 120/min/IP, fails open if Redis is down); `tests/test_rate_limit.py` (6 tests).
> - **1.3** CORS `allow_credentials` set to `False` (bearer auth uses no cookies).
> - **1.4** Added `/health/ready` readiness probe that pings the DB (503 if unreachable); `/health` stays a dependency-free liveness check.
> - **4.5** Removed dead `ADMIN_JWT_SECRET` from config and the env files.
> - **4.6** `email_service` sets the Resend key once at import and uses a bounded 10s HTTP timeout (was a default 30s, re-set per call).
>
> Remaining low-severity items below are not yet addressed: **2.4** (timezone-aware datetimes — repo-wide), **4.2** (upload magic-byte sniffing), **4.3** (escape admin-email HTML), **4.4** (SSRF guard on crawlers), **3.3** (DB pool sizing/recycle), **3.4** (parallelize platform scans), **3.6**/**1.5** (view query count, request-id logging).

---

## Overall Assessment

The backend is **well-structured and disciplined** — clean route/service/model separation, ORM-only (no SQL injection surface), constant-time API-key compare, uniform-404 token gating on the public client view, server-side recomputation of untrusted inputs, and correct field whitelisting that keeps `response_text`/confidence/offsets/tokens off every client-facing surface. CLAUDE.md language and score rules are respected.

The weaknesses are **operational, not architectural**: missing database indexes, two unmet data-retention requirements, and missing timeout/resource limits on the scan pipeline. None are hard to fix.

---

## 1. API Design & Error Handling

**Strengths:** every admin route guards with `Depends(require_api_key)`; Pydantic schemas on all request/response bodies; `MAX_COMPETITORS` and "≥1 platform enabled" enforced; competitor-brief inputs recomputed server-side; client-view uniform 404 on invalid/revoked/archived.

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 1.1 | **No global exception handler.** Unhandled exceptions fall through to FastAPI's default 500 with no consistent error envelope and no logging/trace correlation. Add an `@app.exception_handler` for a uniform `{error, detail}` shape + structlog capture. | Medium | [main.py](backend/app/main.py) |
| 1.2 | **No rate limiting anywhere**, including the public `/view/{token}/*` endpoints, several of which run expensive aggregations (`compute_competitor_intelligence`, `compute_industry_benchmark`). The 256-bit token makes enumeration infeasible, but a *leaked* link can be hammered with no throttle. Add per-IP/per-token limiting (e.g. slowapi) on the view router. | Medium | [client_view.py](backend/app/api/v1/client_view.py) |
| 1.3 | **CORS `allow_credentials=True`** is unnecessary — auth is a bearer token, not cookies — and is paired with `allow_methods=["*"]`/`allow_headers=["*"]`. Not exploitable (origins are explicit) but should be tightened. | Low | [main.py:8-14](backend/app/main.py#L8-L14) |
| 1.4 | **`/health` doesn't probe DB/Redis** — returns `ok` even when Postgres is down (cf. the recent Supabase DNS outage). Add a readiness check that pings the DB. | Low | [main.py:19-21](backend/app/main.py#L19-L21) |
| 1.5 | **No request-id / access logging middleware** — hard to trace a failing request across services. | Low | [main.py](backend/app/main.py) |

---

## 2. Database & Queries

**Strengths:** 100% ORM, fully parameterized — no injection surface. FKs declare `ondelete="CASCADE"`. Win/loss and competitor intelligence read persisted `brand_detected` flags, so they survive raw-response purge ("purge-proof").

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 2.1 | **No indexes on foreign keys or hot filter columns.** Only `clients.share_token` is indexed. Postgres does *not* auto-index FKs, yet nearly every query filters `client_id`/`scan_id` and orders by a `*_at` column. As scan data grows (~112 `scan_query_results` rows per scan), these degrade to sequential scans. Add (ideally composite) indexes — see SQL block below. | **High** | all `models/*.py` |
| 2.2 | **Missing 90-day raw-response purge job.** `RAW_RESPONSE_RETENTION_DAYS = 90` is defined and referenced in comments, but **no task purges `scan_query_results.response_text`**. CLAUDE.md §8 mandates it. Also unbounded TEXT growth. Add a Celery Beat task nulling `response_text` older than 90 days. | **High** | [constants.py:58](backend/app/core/constants.py#L58), no purge task |
| 2.3 | **Missing 6-month post-churn delete.** `archived_at` is set on archive, but nothing hard-deletes client data 6 months later (CLAUDE.md §8). Add a Beat task; rely on the existing `ondelete=CASCADE` FKs to clean children. | Medium | no task; [clients.py:130](backend/app/api/v1/clients.py#L130) |
| 2.4 | **Naive/aware `datetime` mixing.** Models default to `datetime.utcnow` (naive, deprecated in 3.12); `archive_client` writes `datetime.now(timezone.utc)` (aware); `scan_service.has_active_scan` compensates with `.replace(tzinfo=None)`. A direct compare of an aware `archived_at` to a naive `created_at` would raise `TypeError`. Standardize on `DateTime(timezone=True)` + `server_default=func.now()`, or a single `utcnow()` helper. | Medium | [client.py:43](backend/app/models/client.py#L43), [clients.py:130](backend/app/api/v1/clients.py#L130), [scan_service.py:35](backend/app/services/scan_service.py#L35) |
| 2.5 | **Non-atomic `create_client`** — client row and its activity log are committed in two separate transactions; a failure between them leaves a client with no creation log. Wrap in one commit. | Low | [clients.py:44-55](backend/app/api/v1/clients.py#L44-L55) |
| 2.6 | **No `updated_at`** on mutable tables (e.g. `clients` is PATCH-able). Minor observability gap. | Low | [client.py](backend/app/models/client.py) |

Suggested index migration (Alembic):

```sql
CREATE INDEX ix_sqr_scan_id            ON scan_query_results (scan_id);
CREATE INDEX ix_sqr_scan_competitor    ON scan_query_results (scan_id, competitor_id);
CREATE INDEX ix_geo_client_computed    ON geo_scores (client_id, computed_at DESC);
CREATE INDEX ix_scans_client_triggered ON scans (client_id, triggered_at DESC);
CREATE INDEX ix_scans_client_status    ON scans (client_id, status, completed_at DESC);
CREATE INDEX ix_competitors_client     ON competitors (client_id);
CREATE INDEX ix_activity_client_type   ON activity_log (client_id, event_type, created_at DESC);
CREATE INDEX ix_reports_client_period  ON reports (client_id, period_end DESC);
CREATE INDEX ix_traffic_client_period  ON ai_traffic_snapshots (client_id, period);
```

---

## 3. Performance & Scalability

**Strengths:** worker batch tasks (digest, report) isolate per-client failures in their own try/except. Crawlers are bounded (`_MAX_PAGES=15`, `_MAX_CORPUS_CHARS=30k`, non-recursive) with 10s timeouts. Platform retry-once policy (`query_with_retry`) matches the spec. Note: the CLAUDE.md `asyncio.gather(return_exceptions=True)` rule is vacuously satisfied — there is no async fan-out in the codebase.

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 3.1 | **No Celery time limits + no explicit HTTP timeouts on platform clients.** A scan makes up to ~112 sequential provider calls; each client (OpenAI/Anthropic/Gemini) is built with default timeouts (OpenAI ≈600s) and there's no `task_soft_time_limit`/`task_time_limit`. One hung provider + the retry can pin a worker for 10–20 min, blocking the queue. Add global Celery soft/hard limits **and** explicit per-call HTTP timeouts. | **High** | [celery_app.py](backend/workers/celery_app.py), [platform_clients/chatgpt.py:19](backend/app/services/platform_clients/chatgpt.py#L19) |
| 3.2 | **boto3 client rebuilt per call, and called synchronously inside the one `async` route.** `r2_service._s3()` constructs a fresh client each invocation; `upload_client_logo` is `async def` and calls it, blocking the event loop for the upload. Cache the client at module level and either make the endpoint `sync` (FastAPI threadpools it) or offload via `run_in_threadpool`. | Medium | [r2_service.py:6-15](backend/app/services/r2_service.py#L6-L15), [clients.py:91-118](backend/app/api/v1/clients.py#L91-L118) |
| 3.3 | **DB engine has no pool sizing or `pool_recycle`.** Defaults (pool 5 + overflow 10, no recycle) are risky behind the Supabase/Supavisor pooler the team is migrating to. Set `pool_recycle` and size the pool to the pooler; consider distinct config for web vs worker. | Medium | [database.py:6](backend/app/core/database.py#L6) |
| 3.4 | **Platforms scanned strictly sequentially** with `time.sleep(0.5)` between every call. Parallelizing across the 4 platforms (thread pool) would cut scan wall-time ~4×. Acceptable for a background task today; a ceiling as client count grows. | Low–Med | [scan_service.py:135](backend/app/services/scan_service.py#L135) |
| 3.5 | **No `result_expires` on Celery** — task results accumulate in Redis indefinitely. Set an expiry (results aren't read for scans). | Low | [celery_app.py](backend/workers/celery_app.py) |
| 3.6 | **`/view/overview` issues ~10 sequential queries** (history, traffic, benchmark, latest report, 4 existence checks). Fine once indexes (2.1) land; flagged so it isn't forgotten if the view gets heavier. | Low | [client_view.py:103-197](backend/app/api/v1/client_view.py#L103-L197) |

---

## 4. Security & Cross-Cutting

**Strengths:** all secrets via env/`Settings` (none hard-coded); constant-time API-key compare; 256-bit `secrets.token_urlsafe` share tokens with atomic rotation; structlog throughout; client-facing schemas structurally exclude `response_text`, `contact_email`, confidence/offsets/tokens; Telegram alert text is `html.escape`-d.

| # | Finding | Severity | Location |
|---|---------|----------|----------|
| 4.1 | **SVG logo upload without sanitization.** `image/svg+xml` is accepted, stored on R2, and served via the public `logo_url` rendered in the client view. SVG can carry inline `<script>` → **stored XSS** on the client-facing surface. Drop SVG, or sanitize server-side, or serve logos with a restrictive `Content-Security-Policy`/`Content-Disposition`. | Medium | [clients.py:23-29](backend/app/api/v1/clients.py#L23-L29) |
| 4.2 | **Upload content-type is trusted, not verified against bytes.** No magic-byte sniffing — arbitrary bytes can be stored as `image/png`. Admin-only upload limits blast radius. Validate with a sniff (e.g. Pillow open or `filetype`). | Low–Med | [clients.py:100-115](backend/app/api/v1/clients.py#L100-L115) |
| 4.3 | **Unescaped interpolation into alert email HTML.** `response_preview` (raw model output) and `client.name`/`query_text` are injected into HTML email bodies without `html.escape` (the Telegram path *does* escape). Recipient is the admin only, so low blast radius, but raw model output in HTML can break rendering or smuggle markup. Escape all interpolations. | Low–Med | [alert_service.py:293,312-318](backend/app/services/alert_service.py#L293) |
| 4.4 | **SSRF surface in crawlers.** `verification_crawler`/`content_crawler` fetch the admin-entered `website` with `follow_redirects=True` and no host allowlist — a malicious/typo URL (or redirect) could reach `localhost`/`169.254.169.254`. Admin-only input → Low, but add a private-IP/loopback guard before fetching. | Low | [verification_crawler.py:18](backend/app/services/verification_crawler.py#L18), [content_crawler.py:48](backend/app/services/content_crawler.py#L48) |
| 4.5 | **Dead required config: `ADMIN_JWT_SECRET`.** Declared as a mandatory env var but never referenced in the backend (auth uses only `ADMIN_API_KEY`). Forces ops to set a meaningless secret. Remove, or wire up if intended. | Low | [config.py:12](backend/app/core/config.py#L12) |
| 4.6 | **`email_service.send_email` has no timeout/retry and mutates `resend.api_key` globally per call.** Failures are caught at the worker/scan layer (good), but a slow Resend call in a request path has no bound. Set a timeout; set the key once at import. | Low | [email_service.py](backend/app/services/email_service.py) |
| 4.7 | **Single static admin API key, no rotation/expiry.** Acceptable for the single-admin MVP; noted for when access widens. | Low | [auth.py](backend/app/core/auth.py) |

---

## Prioritized Top 10

1. **Add DB indexes on all FK / hot filter columns** (2.1) — biggest performance win, cheap migration.
2. **Add the 90-day raw-response purge job** (2.2) — unmet compliance requirement + storage growth.
3. **Add Celery soft/hard time limits + explicit platform HTTP timeouts** (3.1) — prevents a hung provider from pinning workers.
4. **Sanitize/drop SVG logo uploads** (4.1) — only stored-XSS vector on the client-facing surface.
5. **Add the 6-month post-churn delete job** (2.3) — unmet compliance requirement.
6. **Fix boto3: cache the client + stop blocking the event loop** (3.2).
7. **Standardize datetimes to timezone-aware** (2.4) — removes a latent `TypeError`.
8. **Add a global exception handler + uniform error envelope** (1.1).
9. **Add rate limiting to the public `/view/*` router** (1.2).
10. **Set DB `pool_recycle`/pool sizing for the Supavisor pooler** (3.3) + remove dead `ADMIN_JWT_SECRET` (4.5).

---

## What's Already Solid (don't touch)

- Route/service/model separation and ORM-only data access.
- Auth: constant-time compare, uniform 404 token gating, server-side recomputation of untrusted brief inputs.
- Client-view field whitelisting — no raw responses or internal fields leak.
- Per-platform scan isolation, retry-once policy, and per-client failure isolation in batch tasks.
- Bounded, timeout-guarded crawlers.
- CLAUDE.md language/score-band/`SCORE_VERSION` compliance.
