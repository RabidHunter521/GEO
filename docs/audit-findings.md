# SeenBy codebase audit — findings

Audited 2026-11-10 at commit `e3d0a01`. Findings only; no code was changed.

## Summary

| Severity | Count |
|---|---|
| critical | 2 |
| high | 6 |
| medium | 13 |
| low | 9 |
| **Total** | **30** |

**The five worst**

1. **F-001** — A scan where every scored platform fails but a Google surface answers stores AI Citability **0** and a collapsed Growth Readiness score, which the client then sees.
2. **F-002** — A staff admin can archive a paying client (owner-only) by first flipping `is_prospect` through the ordinary update route. There is no un-archive route.
3. **F-003** — The nightly 6-month churn deletion fails for any client that has Truth Vault facts, and one such client blocks the whole batch, so no churned client is ever deleted.
4. **F-005** — Every public rate limiter is keyed on the Next.js server's IP, so all clients share one 120-requests-a-minute budget; about 11 Overview page loads a minute anywhere in the product start returning error pages.
5. **F-004** — The Claude "what changed this month" narrative appears on the public client Overview as soon as a report is generated, before Faris has reviewed or sent it.

**What was run**

- `pytest -q` (CI env): 2728 passed. `ruff check app workers tests evals`: clean.
- `tsc --noEmit` and `eslint src`: clean. `vitest run`: 23 unit files passed; the 3 Storybook browser files could not start in this sandbox (Chromium build mismatch), so they are not covered.
- `alembic heads`: one head (`ac7cdea98200`).
- A mechanical diff of all 165 TypeScript interfaces against the FastAPI OpenAPI schemas (140 matched by name).
- An OpenAPI sweep of all 184 operations for missing auth.
- Reproductions for F-001, F-002, F-003, F-009, F-011, F-015 and F-027; outputs are quoted in each finding.

**Not covered, and why**

- **Production state.** Nothing here was checked against the Railway database or logs (no access, and §8 forbids substitutes). Whether prod already holds affected rows (for example churned clients older than 180 days, or tracked queries) is unknown.
- **Migrations against real Postgres.** No Postgres server in the sandbox, so `alembic upgrade head`, the model-vs-migration autogenerate diff and the RLS check were not run locally. CI runs all three on Postgres 16; I relied on that plus reading the migrations.
- **`report_service.py` (2,791 lines) and `review_deck_service.py`.** Swept by grep for language, thresholds, weights and the send/generate paths; the PDF HTML builders were not read line by line and no PDF was rendered.
- **Not read in full:** `placement_service`, `provenance_service`, `site_audit_service`, `authority_service`, `misinformation_service`, the benchmark services, the 12 industry packs, and most admin React components. They were covered by the sweeps only (auth, language, thresholds, LLM call sites, contract diff).
- **Live LLM behaviour and evals** were not run (no keys, by design).

---

## Critical

### F-001 · critical · scoring · AI Citability is stored as 0 when all scored platforms fail but a Google surface answers
- **Severity**: critical
- **Confidence**: high
- **Where**: `backend/app/services/scoring_service.py:96-102`; `backend/app/services/scan_service.py:554-585`
- **What's wrong**: `run_scan` only raises "All platforms failed" when there are no result rows at all. If the scored platforms (chatgpt, perplexity, gemini, claude) all fail but `google_aio` or `google_ai_mode` returns rows, `compute_ai_citability` finds no scored platform with status ok and returns `0.0`. That 0 is written to `GeoScore` and the scan is marked completed.
- **Evidence**: Reproduction with five Google rows and `failed_platforms=["chatgpt"]`:
  ```
  breakdown: {'google_aio': {'visibility': 100.0, ..., 'scored': False}, 'chatgpt': {..., 'status': 'unavailable', 'scored': True}}
  ai_citability: 0.0
  ```
  CLAUDE.md §5: "If one platform fails entirely, the scan still completes: score uses the remaining platforms". With no scored platform left there is nothing to score, but a score is written anyway.
- **Impact**: A client with, say, ChatGPT plus Google AI Overviews enabled gets a 40-point drop in the heaviest dimension during an OpenAI outage. The 0 shows on `/view/[token]`, in score history, the PDF and the digest subject, and can fire the score-drop alert and a guarantee transition.
- **Suggested fix**: In `run_scan`, after `compute_platform_breakdown`, treat "no scored platform with status ok" the same as "all platforms failed": raise the existing `RuntimeError` so the scan is marked failed and no `GeoScore` is written. Minimal form: `if not any(e["status"] == "ok" and e.get("scored", True) for e in platform_breakdown.values()): raise RuntimeError(...)`.
- **How to verify the fix**: Add a test in `tests/test_scan_service.py` with one scored platform client raising and a Google client returning rows; assert scan status is `failed` and no `GeoScore` row exists.
- **Fix size**: S

### F-002 · critical · auth · Staff can archive a paying client by flipping `is_prospect` first
- **Severity**: critical (bypass of an owner-only rule; archiving cannot be undone through the app)
- **Confidence**: high
- **Where**: `backend/app/api/v1/clients.py:118-226` (PATCH writes every field), `backend/app/api/v1/clients.py:279` (owner check), `backend/app/schemas/client.py:128` (`is_prospect` in `ClientUpdate`)
- **What's wrong**: `archive_client` requires the owner only when `c.is_prospect` is false. `update_client` lets any admin set `is_prospect`, so staff can PATCH `is_prospect: true` and then DELETE.
- **Evidence**: Reproduction as a staff user against a paying client:
  ```
  direct delete: 403
  patch is_prospect: 200
  delete after patch: 204
  archived_at set: True
  ```
  CLAUDE.md §1: staff can do "everything except managing the team, archiving paying clients and benchmark publishing". No route clears `archived_at`.
- **Impact**: A staff account (or a stolen staff session) can end a paying client's service: the share link 404s, digests and reports stop, and the 180-day deletion clock starts.
- **Suggested fix**: In `update_client`, refuse a change of `is_prospect` from false to true unless `request_identity.is_owner()` (403 otherwise). Converting a prospect to a client (true to false) stays open to staff.
- **How to verify the fix**: Extend `tests/test_owner_only_routes.py` with the PATCH-then-DELETE sequence as staff; expect 403 on the PATCH and `archived_at` still null.
- **Fix size**: S

---

## High

### F-003 · high · retention · Churned-client deletion fails for any client with Truth Vault facts, and blocks the whole batch
- **Severity**: high
- **Confidence**: high (reproduced on SQLite with foreign keys on; Postgres enforces the same constraint)
- **Where**: `backend/app/models/truth_fact.py:99-101`; `backend/alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py:110`; `backend/app/services/retention_service.py:49-72`
- **What's wrong**: `truth_fact_versions.truth_fact_id` references `truth_facts.id` with no `ON DELETE` action and the table has no other cascade path. Deleting a client cascades to `truth_facts`, which the versions still reference, so the delete raises a foreign-key violation. `delete_churned_clients` deletes all due clients in one commit, so one failing client rolls back every other deletion.
- **Evidence**: Reproduction (client archived 200 days ago, one fact, one version):
  ```
  R3 FAILED: IntegrityError (sqlite3.IntegrityError) FOREIGN KEY constraint failed
  ```
  The task catches this and only logs `churned_client_delete_failed` (`workers/tasks/maintenance_tasks.py:46-51`). `tests/test_retention_service.py` only deletes a client with no facts.
- **Impact**: CLAUDE.md §8 ("archived 6 months after churn, then auto-deleted") is not enforced once any churned client has a Truth Vault row. The failure repeats nightly with no admin alert.
- **Suggested fix**: New Alembic migration that drops and recreates the `truth_fact_versions.truth_fact_id` foreign key with `ondelete="CASCADE"`, and the same on the model. Check `misinformation_findings.truth_fact_id` and `truth_fact_version_id` (`models/misinformation_finding.py:42,45`) in the same migration; set them to `SET NULL`. Separately, commit per client inside `delete_churned_clients` with a per-client try/rollback so one bad client cannot block the rest.
- **How to verify the fix**: Add the reproduction above as a test (fact plus version, `PRAGMA foreign_keys=ON`) and assert the client is gone. CI's `alembic upgrade head` / downgrade job covers the migration.
- **Fix size**: M

### F-004 · high · client view · Unreviewed report narrative is shown on the public Overview
- **Severity**: high
- **Confidence**: high
- **Where**: `backend/app/api/v1/client_view.py:415-420`, used at `:634-640`; rendered at `frontend/src/app/view/[token]/page.tsx:293-303`
- **What's wrong**: The Overview takes `change_narrative` from the newest `Report` that has one, with no `sent_at` filter. A report that was generated (by the daily beat or by hand) but not yet reviewed and sent already publishes its Claude narrative on the share view.
- **Evidence**: `.filter(Report.client_id == client.id, Report.change_narrative.isnot(None))`. The same file's `/reports` endpoint filters `Report.sent_at.isnot(None)` with the comment "Only reports that have actually been delivered", and the activity whitelist comment says "internal pre-review report builds never reach this surface". CLAUDE.md §7: "You (Faris) review before sending".
- **Impact**: Unreviewed LLM prose about the client's month is visible to the client from the moment the 9am beat generates the PDF.
- **Suggested fix**: Add `Report.sent_at.isnot(None)` to the `latest_report` query.
- **How to verify the fix**: Test in `tests/test_api_client_view.py`: an unsent report with a narrative gives `change_narrative is None`; after setting `sent_at` it appears.
- **Fix size**: S

### F-005 · high · rate limiting · All public rate limits are one shared bucket keyed on the Next.js server
- **Severity**: high
- **Confidence**: high on the mechanism; medium on the exact production threshold (depends on how the frontend reaches the API on Railway)
- **Where**: `frontend/src/lib/view-api.ts:30-33,128-133`; `frontend/src/lib/api.ts:63-68`; `frontend/src/app/view/action-approval/[token]/page.tsx:29,52`; `backend/app/core/rate_limit.py:60-76`; limits at `backend/app/api/v1/client_view.py:359`, `action_approvals.py:35`, `attribution.py:44-45`, `scans.py:35`, `core/rate_limit.py:115`
- **What's wrong**: Every `/view/*` page is rendered by the Next.js server, which calls the API without forwarding the visitor's address. `_client_ip` therefore resolves to the Next.js server for every visitor, so "120/min per IP" is 120/min for all clients combined. One Overview load makes 11 API calls (layout: `overview`, `visit`; page: 9 more).
- **Evidence**: `viewFetch` sends only `cache: "no-store"`. Count from `src/app/view/[token]/layout.tsx` and `page.tsx`: 2 + 9 calls. A 429 is not a 404, so `viewFetch` throws and the client gets the error page.
- **Impact**: Roughly 11 Overview loads a minute across the whole product (admin previews included) exhaust the budget and clients see errors. The same applies to action approvals (30/min total), the webhook relay (120/min total), LLM generation (20/min across all admins) and scan triggers (10/min across all admins). The limiter also cannot single out an abusive visitor.
- **Suggested fix**: NEEDS DECISION on the trust model. Simplest safe option: have the Next.js server send the visitor IP in a dedicated header (as `/wa/[token]` already does with `X-Visitor-IP`) and have the limiter use it only when the request also carries the service key, so it cannot be spoofed by direct API callers. Until then, raising the `client_view` limit is a stopgap.
- **How to verify the fix**: Test in `tests/test_rate_limit.py`: two different forwarded visitor IPs from the same peer get separate budgets; the header without the service key is ignored.
- **Fix size**: M

### F-006 · high · client output · Overview and PDF describe measurements SeenBy does not make
- **Severity**: high
- **Confidence**: high
- **Where**: `frontend/src/app/view/[token]/page.tsx:46-64`; `backend/app/services/report_service.py:78-83` (used at `:928-939`)
- **What's wrong**: The client Overview says Technical Foundations "Reviews the technical health of your website, including page speed, crawlability, mobile experience, security, and accessibility" and that Brand Authority is based on "backlinks". The PDF fallback notes say "Based on brand presence, reviews, backlinks and industry recognition" and "content depth, accuracy, freshness". None of page speed, mobile experience, security, accessibility, backlinks or freshness is measured.
- **Evidence**: CLAUDE.md §4: Technical Foundations "is driven by verified robots.txt AI-crawler access". `methodology_service.py:61`: "Whether your robots.txt lets AI crawlers read your site." `ASSESSMENT_RUBRICS` (`constants.py:61-86`) has no backlink or freshness criterion. The PDF prints the fallback note next to "Not yet reviewed", so it states a basis for a dimension nobody reviewed.
- **Impact**: The Overview contradicts the methodology page linked from the same score breakdown. A client scoring 100 on Technical Foundations is told their page speed and security were reviewed.
- **Suggested fix**: Replace the five hardcoded descriptions with text from the `/methodology` payload (already derived from constants), or at minimum rewrite them to match `methodology_service`. In the PDF, print no basis note when the dimension is not reviewed, and reword the two fallbacks to the rubric's actual criteria.
- **How to verify the fix**: Grep the view page and `report_service.py` for "page speed", "backlinks", "freshness": no hits. Render the Overview and the PDF for a client with an unreviewed dimension.
- **Fix size**: M

### F-007 · high · digest · "First time AI models saw your brand!" fires when it is not the first time
- **Severity**: high
- **Confidence**: high
- **Where**: `backend/app/services/digest_service.py:282-297`, rendered at `:498-507`
- **What's wrong**: `_detect_first_seen` only checks the immediately previous completed scan. A client seen in March, not seen in April and seen again in May gets the "first time" milestone in May. It also compares a scored-platform count for this scan against an all-platform count for the previous one.
- **Evidence**: `return prev_detected == 0`, where `prev_detected` counts only `prev_scan.id` rows.
- **Impact**: A false milestone in an automated email that nobody reviews.
- **Suggested fix**: Query whether any earlier completed scan for the client has a client-owned, non-control row with `brand_detected` true (join `ScanQueryResult` to `Scan` on `client_id`, `completed_at < latest`). Apply `scored_results` to both sides or neither.
- **How to verify the fix**: Test in `tests/test_digest_service.py` with three scans (seen, not seen, seen): expect `False`.
- **Fix size**: S

### F-008 · high · retention · Churn deletion leaves the client's PDFs and logo in R2
- **Severity**: high
- **Confidence**: high
- **Where**: `backend/app/services/retention_service.py:49-72`; `backend/app/services/r2_service.py` (no delete function)
- **What's wrong**: `delete_churned_clients` removes database rows only. Report PDFs under `reports/{client_id}/` in the private bucket and the logo in the public bucket are never deleted, and once the `reports` rows are gone nothing references the keys.
- **Evidence**: `grep -rn "delete_object" backend/app backend/workers` returns nothing.
- **Impact**: Client reports (scores, competitor data, AI answer excerpts) outlive the §8 "then auto-deleted" promise indefinitely. Depends on F-003 being fixed before it matters in practice.
- **Suggested fix**: Add `r2_service.delete_prefix(prefix)` (list plus `delete_objects`) and a logo delete by key. Call them in `delete_churned_clients` before `db.delete(client)`; on an R2 error, skip that client and log, so rows and objects stay consistent.
- **How to verify the fix**: Test with a mocked S3 client asserting `delete_objects` is called with the client's report keys and logo key.
- **Fix size**: M

---

## Medium

### F-009 · medium · security · Approval and WhatsApp tokens are logged unredacted; the error handler logs raw share tokens
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/app/core/logging.py:13`; `backend/app/main.py:73`
- **What's wrong**: `_SECRET_PATH` redacts `/auth/link/`, `/auth/invite/` and `/view/` only. `/api/v1/action-approvals/{token}` (a credential that approves client work) and `/api/v1/track/whatsapp/{token}` are logged in full. Separately, `unhandled_exception_handler` passes `path=request.url.path`, overriding the redacted path bound by the middleware.
- **Evidence**:
  ```
  /api/v1/view/AAAAAAAAAAAAAAAAAAAAAAAA/overview -> /api/v1/view/AAAAAA…/overview
  /api/v1/action-approvals/SECRETTOKEN1234567890 -> /api/v1/action-approvals/SECRETTOKEN1234567890
  /api/v1/track/whatsapp/CLICKTOKEN1234567890 -> /api/v1/track/whatsapp/CLICKTOKEN1234567890
  ```
- **Impact**: Anyone with log access can approve an outcome action on a client's behalf, or read a live share token after any 500 on a view route.
- **Suggested fix**: Add `/action-approvals/` and `/track/whatsapp/` to `_SECRET_PATH`; use `redact_path(request.url.path)` in `main.py:73`.
- **How to verify the fix**: Unit test `redact_path` on the three paths above.
- **Fix size**: S

### F-010 · medium · auth · A password and 2FA reset does not end existing sessions
- **Severity**: medium
- **Confidence**: high (code reading; not exercised end to end)
- **Where**: `frontend/auth.ts:100-125` (7-day JWT session); `frontend/src/lib/api-token.ts:27-36` (claims: `sub`, `wid` only); `backend/app/core/auth.py:46-70`; `backend/app/services/user_service.py:122-136`
- **What's wrong**: The API re-loads the user on each request and checks `is_usable`. `issue_reset` makes the account unusable, but once the admin completes the new link it is usable again, and a NextAuth session cookie issued before the reset mints valid API tokens again for the rest of its 7 days.
- **Evidence**: Nothing ties a session to a credential version: the per-request token carries no login time, and `User` has no such column.
- **Impact**: The "lost phone / suspected compromise" reset does not lock out whoever holds the old session.
- **Suggested fix**: Add `credentials_changed_at` to `User` (set in `accept_link`). Put the login time in the NextAuth JWT, pass it as a claim in `mintUserToken`, and reject tokens whose login time is earlier than `credentials_changed_at`. Needs a migration.
- **How to verify the fix**: Test in `tests/test_request_identity.py`: a token with a login time before `credentials_changed_at` returns 401.
- **Fix size**: M

### F-011 · medium · scoring · Repeat tracked-query samples are counted in the score and shown as duplicate rows
- **Severity**: medium
- **Confidence**: high on behaviour; low on exposure (there is no UI to create tracked queries, see F-026)
- **Where**: `backend/app/services/scan_service.py:302-358`; `backend/app/services/scoring_service.py:49-76`; `backend/app/services/digest_service.py:174-185`; `backend/app/api/v1/client_view.py:895-904`
- **What's wrong**: Tracked-query samples are stored as ordinary client rows (`competitor_id` null, not control) with up to 3 repeats per platform. Nothing filters on `tracked_query_id`, so a recommendation or local tracked question counts up to three times in AI Citability, in the digest's "seen X of Y", and appears as repeated identical rows on the client scan page.
- **Evidence**: Reproduction: four unseen discovery rows score 0.0; adding three repeat samples of one seen tracked question scores 42.86. CLAUDE.md §4 and §5 describe the score as built from the generated question set and do not mention samples.
- **Impact**: For a client with tracked queries, one high-risk question outweighs three ordinary ones, and counts shown to the client include repeats.
- **Suggested fix**: NEEDS DECISION (this is a §4 formula question). If samples should not count: exclude rows with `tracked_query_id` set in `compute_platform_breakdown`, the flat fallback in `compute_ai_citability`, the digest counts and the client scan list. If that changes any existing client's score it needs a SCORE_VERSION bump.
- **How to verify the fix**: Test in `tests/test_scoring_service.py` using the reproduction above.
- **Fix size**: M

### F-012 · medium · workers · Benchmark generation task is never registered or scheduled
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/workers/celery_app.py:10-16` (include list), `:34-51` (beat schedule); `backend/workers/tasks/benchmark_tasks.py`
- **What's wrong**: `workers.tasks.benchmark_tasks` is not in Celery's `include` and has no beat entry. The worker never imports it, so the task cannot even be called by name, although its docstring says "Scheduled generation" and `docs/ops/benchmark-privacy-runbook.md:95-99` tells the operator to run it monthly.
- **Evidence**: `grep -rn "benchmark_tasks" backend --include=*.py` matches only the task file itself.
- **Impact**: Cohort snapshots are never produced, so `/benchmarks` and the client view cohort comparison stay empty.
- **Suggested fix**: Add `"workers.tasks.benchmark_tasks"` to `include`. Add a monthly beat entry (for example the 2nd of the month, 05:00 UTC) or state in the runbook that it is manual and how to invoke it. Add start and end logs are already present.
- **How to verify the fix**: `poetry run python -c "from workers.celery_app import celery_app; celery_app.loader.import_default_modules(); print('workers.tasks.benchmark_tasks.generate_monthly_benchmarks' in celery_app.tasks)"` prints `True`.
- **Fix size**: S

### F-013 · medium · reports · A failed report build is silent
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/workers/tasks/report_tasks.py:15-23` and `:55-66`
- **What's wrong**: When `generate_report_pdf` raises (WeasyPrint, R2, data), the manual task just fails in Celery and the daily task only writes a log line. There is no activity-log row and no admin alert. A `None` return (no scan data, prospect) is also only logged.
- **Evidence**: `seenby-client-output` rule 6: "A report that fails to generate must alert (activity log + admin email)". No `report_failed` event type exists in `KNOWN_ACTIVITY_EVENT_TYPES`.
- **Impact**: A client's monthly report can silently never appear; the admin UI keeps promising an update.
- **Suggested fix**: Wrap both call sites: on exception, `db.rollback()`, add an `ActivityLog` (`event_type="report_failed"`, registered in the four dashboard maps in `constants.py`), commit, and call `alert_service.dispatch_admin_alert` inside its own try/except.
- **How to verify the fix**: Test with `generate_report_pdf` patched to raise: one `report_failed` activity row and one `send_email` call to `ALERTS_EMAIL`.
- **Fix size**: M

### F-014 · medium · reports · One unsent report stops automatic monthly reports for that client permanently
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/workers/tasks/report_tasks.py:46-51,73-80`; `backend/app/api/v1/reports.py` (no delete route)
- **What's wrong**: The daily job skips any client with a report where `sent_at` is null. There is no way to discard a report, so a draft Faris decides not to send (or an old manual test build) blocks auto-generation for that client until it is sent.
- **Evidence**: `_has_unsent_report` has no age limit; `reports.py` exposes only generate, list, send, scorecard and review-deck.
- **Impact**: The "every 30 days" cadence (§7) silently stops for affected clients; the skip is counted but not surfaced.
- **Suggested fix**: NEEDS DECISION between (a) a `DELETE /clients/{id}/reports/{report_id}` route for unsent reports that also removes the R2 object, or (b) ignoring unsent reports older than 30 days in `_has_unsent_report`. (a) is cleaner.
- **How to verify the fix**: Test in `tests/` for report tasks: with an old unsent report present, the due check behaves per the chosen option.
- **Fix size**: M

### F-015 · medium · contract · `enabled_platforms` sent on client creation is silently dropped
- **Severity**: medium
- **Confidence**: high
- **Where**: `frontend/src/app/(admin)/clients/actions.ts:45-51`; `frontend/src/lib/api.ts` `createClient`; `backend/app/schemas/client.py:86-92`
- **What's wrong**: `createProspectAction` posts `enabled_platforms: ["chatgpt", "perplexity"]`, but `ClientCreate` has no such field, so the value is discarded and the model default (all six platforms) applies.
- **Evidence**: Reproduction: POST with `enabled_platforms: ["chatgpt","perplexity"]` returns `201 ['chatgpt', 'perplexity', 'gemini', 'claude', 'google_aio', 'google_ai_mode']`.
- **Impact**: Every prospect scan runs on six platforms instead of two, about three times the intended cost per cold lead.
- **Suggested fix**: Add `enabled_platforms: list[str] | None = None` to `ClientCreate` with the same validator as `ClientUpdate`, and drop the key from the dump when it is `None` so the model default still applies.
- **How to verify the fix**: Re-run the reproduction; expect `['chatgpt', 'perplexity']`. Add it to `tests/test_api_clients.py`.
- **Fix size**: S

### F-016 · medium · score colour · Client score-history bars use band colours, not the traffic light
- **Severity**: medium
- **Confidence**: high
- **Where**: `frontend/src/components/view/ScoreHistoryChart.tsx:39,51`; `frontend/src/lib/score-utils.ts:4-10`
- **What's wrong**: The chart colours each bar with `getScoreBand(score).color`, where "good" (65-79) is green and "low" (0-34) is red. The traffic light (§3) makes 65-69 yellow and 30-34 yellow.
- **Evidence**: `fill={`hsl(${BAND_TOKEN[band.color]})`}`. Every other caller uses `getScoreBand(...).name` only.
- **Impact**: A client at 67 sees a yellow headline score and a green bar for the same number on the same page.
- **Suggested fix**: Use `getScoreColor(clamped)` in the chart. Then remove the `color` field from the `SCORE_BANDS` array and the `ScoreBand` type so it cannot be reused (see F-026).
- **How to verify the fix**: `npx tsc --noEmit`; render the Overview for history points 67 and 32 and check both bars are yellow.
- **Fix size**: S

### F-017 · medium · language · Some LLM text shown to clients skips the sanitizer
- **Severity**: medium
- **Confidence**: high that the fields are unsanitized; no leak was observed
- **Where**: `backend/app/services/content_roadmap_service.py:75-76,81,87` (`suggested_title`, `theme`, `content_type`) and `:97-118` (`article_content`); `backend/app/services/content_analysis_service.py:86-91` (`topic`, `title` of suggestions)
- **What's wrong**: Only `rationale` is passed through `sanitize_text`. The other fields are returned by `/view/{token}/roadmap` and `/view/{token}/content-gaps` and rendered on the Action Plan page.
- **Evidence**: `seenby-prompts` rule 2: "the service must run `language_sanitizer.sanitize_text()` on the output as a second line of defense."
- **Impact**: A title such as "Why you are not mentioned by ChatGPT" would reach the client view unchanged.
- **Suggested fix**: Sanitize `suggested_title`, `theme` and the suggestion `topic`/`title`. For `article_content`, NEEDS DECISION: it is a draft for the client's own site, where "cited" can be legitimate; sanitizing could corrupt it (see F-027).
- **How to verify the fix**: Tests with a mocked response containing "mentioned" in the title; assert the stored value says "seen by AI".
- **Fix size**: S

### F-018 · medium · constants · Dimension weights are retyped in the PDF and the client Overview
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/app/services/report_service.py:960-970`; `frontend/src/app/view/[token]/page.tsx:42,47,52,57,62`; duplicate colour thresholds at `backend/app/services/report_service.py:886-891`
- **What's wrong**: "40%", "20%", "20%", "10%", "10%" are string literals in both places, and `_build_gauge_svg` repeats the 70/30 colour cut-offs instead of calling `get_score_color`. The same dimension is also named three ways on client surfaces: "AI Citability" (PDF), "AI Presence" (Overview), "AI Visibility Frequency" (digest).
- **Evidence**: CLAUDE.md §4: "Never change weights without updating this file"; §9 says methodology content is "derived from constants ... never retyped". `SCORE_WEIGHTS` is the source.
- **Impact**: A weight change would leave the PDF and Overview showing the old weights next to a methodology page showing the new ones.
- **Suggested fix**: Backend: format from `SCORE_WEIGHTS` (`f"{SCORE_WEIGHTS['ai_citability']:.0%}"`) and call `get_score_color` in the gauge. Frontend: take weights from the `/methodology` payload. The naming question is NEEDS DECISION (pick one client-facing name).
- **How to verify the fix**: `grep -n '"40%"\|"20%"\|"10%"' backend/app/services/report_service.py "frontend/src/app/view/[token]/page.tsx"` returns nothing.
- **Fix size**: M

### F-019 · medium · alerts · An email failure also suppresses the Telegram alert
- **Severity**: medium
- **Confidence**: high
- **Where**: `backend/app/services/alert_service.py:27-32`
- **What's wrong**: `_dispatch_admin_alert` calls `send_email` and then `send_telegram`. If Resend raises, Telegram is never reached, and the caller's catch-all swallows the whole alert.
- **Evidence**: §7: "Always email ALERTS_EMAIL; also push to Telegram ... (best-effort, never blocks a scan)". Telegram exists as the second channel for exactly this case.
- **Impact**: During a Resend outage, score-drop, overtake and budget alerts are lost on both channels.
- **Suggested fix**: Wrap `send_email` in try/except, call `send_telegram` regardless, then re-raise the email error so existing callers behave as before.
- **How to verify the fix**: Test in `tests/test_alert_service.py`: `send_email` raises, assert `send_telegram` was still called.
- **Fix size**: S

### F-020 · medium · scans · The 15-minute reaper can fail a scan that is still running
- **Severity**: medium
- **Confidence**: medium (depends on real scan duration, which I could not measure)
- **Where**: `backend/app/services/scan_service.py:88-122` and `:597-599`; `backend/workers/celery_app.py:28-29`; `backend/app/core/constants.py:281-283`
- **What's wrong**: Scans older than `ACTIVE_SCAN_STALE_MINUTES` (15) are flipped to `failed` and stop blocking new triggers, but the Celery limit is 25/30 minutes. A slow scan (six platforms, retries waiting up to 30 seconds each) can still be running. The worker later overwrites the status with `completed`, leaving a "scan failed" activity row for a completed scan, and a second scan may have been started in between.
- **Evidence**: The constant's own comment assumes "A full 4-platform scan takes ~2 min"; there are now six platforms, up to 28 pack questions, tracked samples and competitor questions per platform.
- **Impact**: Contradictory activity log, possible overlapping scans and double spend for one client.
- **Suggested fix**: Make the two limits agree: either raise `ACTIVE_SCAN_STALE_MINUTES` above `task_time_limit` (for example 35), or have `run_scan` re-read the scan status before writing results and abort if it is already `failed`.
- **How to verify the fix**: Assert in a test that `ACTIVE_SCAN_STALE_MINUTES * 60 > celery_app.conf.task_time_limit`, or test the abort path.
- **Fix size**: S

### F-021 · medium · workers · Batch loops do not roll back after a failed client
- **Severity**: medium
- **Confidence**: medium (needs a database-level error to trigger)
- **Where**: `backend/workers/tasks/digest_tasks.py:35-41`; `backend/workers/tasks/report_tasks.py:60-66`; `backend/workers/tasks/content_tasks.py:54-58,96-100`
- **What's wrong**: The digest and report loops catch a per-client exception but do not call `db.rollback()`. If the failure was a flush or commit error, the shared session stays in a failed transaction and every later client in the batch fails too. In `content_tasks`, the except block sets `status = "failed"` and commits without rolling back first, so the status update itself can fail and the row stays `running`.
- **Evidence**: §10: "isolate each unit so one failure can't sink the batch" and "must catch, `db.rollback()`, and swallow". `scan_service.run_scan` does this correctly at `:718`.
- **Impact**: One bad client can cancel the Monday digest or the daily report run for everyone after it.
- **Suggested fix**: Add `db.rollback()` as the first line of each of the four except blocks.
- **How to verify the fix**: Test with a session whose first client raises `sqlalchemy.exc.IntegrityError` during commit; assert the second client is still processed.
- **Fix size**: S

---

## Low

### F-022 · low · client view · Two public endpoints are served but used by no page
- **Severity**: low
- **Confidence**: high
- **Where**: `backend/app/api/v1/client_view.py:1090-1112` (`/toolkit`), `:1190-1216` (`/activity`)
- **What's wrong**: `frontend/src/lib/view-api.ts` has no caller for either. `/activity` returns raw `ActivityLog.note` text, which is written for admins (for example "Scan completed. AI Citability: 43.0." and "Monthly report sent to <email>").
- **Evidence**: The endpoint-usage sweep found no reference to `/view/{token}/toolkit` or `/view/{token}/activity` in `frontend/src`. `ClientViewTrafficValue.at_risk_*` (`schemas/client_view.py:95-97`) is likewise sent but absent from the TypeScript type.
- **Impact**: Unreviewed admin wording is reachable with a share token; extra public surface to maintain.
- **Suggested fix**: Remove both routes and their schemas, or drop `note` from `ClientViewActivity`. Remove the three `at_risk_*` fields from the public schema if no page will use them.
- **How to verify the fix**: `pytest tests/test_api_client_view.py`; requests to the removed paths return 404.
- **Fix size**: S

### F-023 · low · api · Explicit `null` on a required client field returns 500
- **Severity**: low
- **Confidence**: medium (read from code, not run)
- **Where**: `backend/app/api/v1/clients.py:184-185`; `backend/app/schemas/client.py:95-135`
- **What's wrong**: `ClientUpdate` types every field as optional and the route writes each sent key with `setattr`. A body such as `{"name": null}` or `{"scan_cadence_days": null}` sets a NOT NULL column to `None` and fails at commit with an unhandled `IntegrityError`.
- **Evidence**: `for field, value in updates.items(): setattr(c, field, value)` with `exclude_unset=True` (explicit nulls are kept).
- **Impact**: A cleared number input in the settings form produces "Internal server error" instead of a validation message.
- **Suggested fix**: Before the loop, drop keys whose value is `None` for non-nullable columns (`name`, `website`, `industry`, `is_prospect`, `score_drop_threshold`, `scan_cadence_days`, `visitor_to_lead_pct`, `lead_to_customer_pct`, `benchmark_opt_out`, `win_notifications_enabled`), or return 422.
- **How to verify the fix**: `PATCH /api/v1/clients/{id}` with `{"name": null}` returns 200 (unchanged) or 422, not 500.
- **Fix size**: S

### F-024 · low · auth · Twenty failed logins lock every admin out for 15 minutes
- **Severity**: low
- **Confidence**: high
- **Where**: `frontend/auth.ts:15-25,40-45`
- **What's wrong**: The global counter blocks all sign-ins once 20 failures occur in 15 minutes, whatever the email. Anyone on the internet can keep it tripped. The counters are also per-process memory, so they reset on deploy and are not shared between instances.
- **Evidence**: `globalFailures.count >= MAX_GLOBAL_FAILED_ATTEMPTS` returns locked for any key.
- **Impact**: Cheap denial of sign-in for the whole team. Existing sessions keep working.
- **Suggested fix**: NEEDS DECISION. The backend already locks per account (`user_service.authenticate`); either drop the global counter or replace it with a per-IP one.
- **How to verify the fix**: Manual: 20 bad logins for one email do not block a correct login for another.
- **Fix size**: S

### F-025 · low · docs drift · CLAUDE.md, architecture.md and comments that no longer match the code
- **Severity**: low
- **Confidence**: high
- **Where** (each is a separate one-line fix):
  - `docs/architecture.md:3,14` — dated 2026-07-29 and says the frontend sends "bearer ADMIN_API_KEY"; it now sends a per-user signed token (`core/auth.py`). The task table omits `benchmark_tasks`.
  - `backend/app/core/constants.py:232` ("MVP runs on-demand scans only") and `:331` ("nothing auto-scans (§11)") — §11 now allows scheduled scans. Still true in practice (none are built), but the stated reason is stale.
  - `backend/app/api/v1/clients.py:210` and `backend/app/services/report_service.py:77` — refer to the retired label "Assessed by SeenBy team".
  - `.claude/skills/seenby-client-output/SKILL.md:19` — "Manual dimensions always carry 'Based on public evidence · Reviewed by SeenBy'" contradicts §4 ("Not yet reviewed" until accepted). §4 and the code are right.
  - `backend/app/core/database.py:6` — comment mentions the Supavisor pooler.
  - `backend/.superpowers/sdd/progress.md:23` (tracked in git) — says "`backend/.env` points at PRODUCTION Supabase", which §8 states is false and dangerous to believe.
  - CLAUDE.md §9 — pages that exist but are not listed: `/view/action-approval/[token]`, `/review-queue/legacy-work-log`, and the route handlers `/api/clients/[id]/scorecard`, `/api/clients/[id]/review-deck`, `/clients/[id]/scan/snippet/[scanId]/[resultId]`.
  - CLAUDE.md §10 ("All API calls through `src/lib/api.ts`") — the code deliberately uses four more fetch modules (`view-api.ts`, `tracking-api.ts`, `auth-api.ts`, `auth.ts`) plus direct `fetch` in `view/action-approval/[token]/page.tsx:29,52` and the three route handlers above. The rule should name the allowed modules; the page-level fetches should move into `view-api.ts`.
  - CLAUDE.md §7 ("ONLY when score changes ±5pts") — the code triggers on AI Citability, not Growth Readiness (`claude_action.py:31-36`, `constants.py:292`). The code looks intentional; §7 should say "AI Citability".
  - `backend/app/api/v1/client_view.py:1` and `backend/app/services/retention_service.py:1` — an import sits above the module docstring, so the docstring is not one.
- **What's wrong**: Each statement disagrees with current behaviour.
- **Evidence**: As listed.
- **Impact**: Misleads the next person or model; the Supabase line could repeat the 2026-09-09 misdiagnosis.
- **Suggested fix**: Edit each line to match the code. For the three CLAUDE.md items, I think the code is right and the doc should change.
- **How to verify the fix**: Re-read the listed lines.
- **Fix size**: S

### F-026 · low · dead code · Unused constants, duplicated helpers and API surface with no caller
- **Severity**: low
- **Confidence**: high
- **Where**:
  - `backend/app/core/constants.py:100-108` — `SCORE_COLOR_THRESHOLDS` and `SCORE_COLORS` are imported nowhere; `SCORE_COLORS` contradicts the traffic light (good = green). `get_score_color` (`scoring_service.py:126-134`) hardcodes 70/30 instead of the thresholds constant.
  - `frontend/src/lib/score-utils.ts:4-10` — the `color` field on bands (see F-016).
  - `_safe_public_url` duplicated verbatim in `backend/app/api/v1/client_view.py:234-249` and `backend/app/api/v1/action_approvals.py:48-63`.
  - `backend/app/services/report_service.py:2710-2716` sends through `resend` directly with its own hardcoded sender instead of `email_service.send_email`.
  - Backend routes with no frontend caller: all of `tracked_queries.py`, `conversion_events.py`, `search_console.py`, `costs.py`, `market_intelligence.py`; `POST /digest/trigger/{client_id}`; `GET /scans/{scan_id}`; `GET /outcome-actions/review-queue`; `GET /clients/{id}/truth-facts/{fact_id}`; `GET .../deliverables/{id}/download`; all of `benchmark_publications.py` and `GET /public/benchmarks/{slug}` (no admin UI and no public page).
- **What's wrong**: Code that is unreachable from the product or duplicates another definition.
- **Evidence**: Endpoint-usage sweep (OpenAPI paths against every `/api/v1/...` string in `frontend/src`) and `grep -rn "SCORE_COLORS\|SCORE_COLOR_THRESHOLDS" backend/app backend/workers` (constants file only).
- **Impact**: Tracked queries and benchmark publishing are features that cannot be used without calling the API by hand. The rest is maintenance weight.
- **Suggested fix**: Delete `SCORE_COLORS`; make `get_score_color` read `SCORE_COLOR_THRESHOLDS`; move `_safe_public_url` to `app/services/url_safety.py`; route the report email through `send_email` (it needs an attachments parameter). The orphaned routes are NEEDS DECISION: build the UI or remove them.
- **How to verify the fix**: `pytest -q` and `ruff check` stay green.
- **Fix size**: M

### F-027 · low · language · Sanitizer output is ungrammatical and one static tip uses "mentions"
- **Severity**: low
- **Confidence**: high
- **Where**: `backend/app/services/language_sanitizer.py:12-21`; `backend/app/core/constants.py:301`; admin-only wording at `backend/app/services/provenance_service.py:462-464`, `backend/app/services/outcome_priority_service.py:70`, `frontend/src/components/delivery/ActionDetailDialog.tsx:95`, `frontend/src/components/competitors/ShareOfSourceSection.tsx:117`
- **What's wrong**: The replacements are literal, so sentences break; "citation", "citations", "cites" and "mentions" are not covered although `LANGUAGE_RULES` bans "citation". The "low" band digest tip, emailed to clients without the sanitizer, ends "consistent contextual mentions". The admin-only strings use "cites", "visibility gap" and "Confidence".
- **Evidence**:
  ```
  'Close the visibility gap by adding FAQs.' -> 'Close the Your competitors are winning here by adding FAQs.'
  'You were cited by ChatGPT.' -> 'You were seen by AI by ChatGPT.'
  'Your citation rate rose; 3 citations and 2 mentions.' -> 'Your visibility frequency rose; 3 citations and 2 mentions.'
  ```
- **Impact**: Awkward client-facing sentences when the fallback fires; one borderline word in a client email. The admin-only items do not reach clients.
- **Suggested fix**: Reword the tip (for example "... recognise brands that are described consistently across your site"). Change the `visibility gap` replacement to a noun phrase that fits mid-sentence and add patterns for `citations?` and `cited by` — wording is NEEDS DECISION since §2 fixes the exact replacement text.
- **How to verify the fix**: Extend `tests/test_language_sanitizer.py` with the three sentences above.
- **Fix size**: S

### F-028 · low · observability · Small gaps in logging and error handling
- **Severity**: low
- **Confidence**: high
- **Where**:
  - `backend/app/services/claude_action.py:37-40` — `except Exception: pass` hides every digest-action failure with no log line.
  - `backend/workers/tasks/scan_tasks.py:11-19` — no end log, and the task returns `{"status": "completed"}` even when `run_scan` marked the scan failed.
  - `backend/app/core/rate_limit.py:86-88` — `INCR` then `EXPIRE` are separate calls; if the process dies between them the key never expires and that IP is blocked until Redis is flushed.
  - `backend/app/core/constants.py:669` — `citation_flip` (a source newly naming the client, good news) is in the "attention" tier, defined as "something failed or moved against the client".
- **What's wrong**: Failures are hidden or state is misreported.
- **Evidence**: As listed.
- **Impact**: Harder diagnosis; a rare permanent 429; a positive event shown as a problem on the dashboard.
- **Suggested fix**: Log a warning in the except block; log end and return the scan's real status; use `SET key 1 EX window NX` then `INCR`, or a pipeline; move `citation_flip` to the notable tier (the comment at `constants.py:700` says the attention set is spec-locked, so this is NEEDS DECISION; `tests/test_dashboard_constants.py` must stay green).
- **How to verify the fix**: `pytest tests/test_claude_action.py tests/test_rate_limit.py tests/test_dashboard_constants.py`.
- **Fix size**: S

### F-029 · low · reports · Send and generate routes skip state checks
- **Severity**: low
- **Confidence**: high
- **Where**: `backend/app/api/v1/reports.py:89-117` and `:156-168`; `backend/app/services/report_service.py:2693-2727`
- **What's wrong**: `send_report` does not check that the client is still active, so a report can be emailed to an archived client. `generate_report` returns "queued" for a prospect although the task then skips it. Two near-simultaneous send requests can both pass the `sent_at is None` check and email twice.
- **Evidence**: `send_report` loads the `Report` only; `send_report_email` checks `contact_email` only.
- **Impact**: Rare wrong email; a confusing "queued" that never produces a report.
- **Suggested fix**: 404 in `send_report` when the client is archived; 409 in `generate_report` when `is_prospect`; lock the row in `send_report_email` with `with_for_update()` before the check.
- **How to verify the fix**: Tests in `tests/test_api_report_generate.py` for the archived and prospect cases.
- **Fix size**: S

### F-030 · low · tests · Critical paths with no test
- **Severity**: low
- **Confidence**: high
- **Where**: `backend/tests/`
- **What's wrong**: The suite is large and its assertions are meaningful (only 6 of about 2,700 tests have no assertion, all deliberate "does not raise" checks). The gaps are the cases behind the findings above: no scan test where only reported-only platforms answer (F-001); no staff PATCH-then-DELETE test (F-002); retention is tested only on a client with no child rows (F-003); no test that an unsent report's narrative stays private (F-004); no rate-limit test behind a proxying frontend (F-005); first-seen is tested with at most one prior scan (F-007); nothing covers tracked samples in scoring (F-011) or report-build failure alerting (F-013). The 3 Storybook browser test files did not run here.
- **Evidence**: `grep -n "truth\|TruthFact" tests/test_retention_service.py` and `grep -n "sample\|tracked" tests/test_scoring_service.py` both return nothing.
- **Impact**: Each of these bugs passed CI.
- **Suggested fix**: Add the test named in each finding's "How to verify" along with its fix.
- **How to verify the fix**: The new tests fail before each fix and pass after.
- **Fix size**: M

---

## Not a bug, but worth knowing

- **Admin auth coverage is complete.** Of 184 API operations, the only ones without admin auth are the 22 `/view/{token}/*` routes, `/action-approvals/{token}`, `/track/whatsapp/{click_token}`, `/webhooks/heard-about-us`, `/public/benchmarks/{slug}` and the two health checks. Team routes and benchmark publishing use `require_owner`.
- **Share-token gating is uniform.** Invalid, revoked, expired, archived and wrong-length tokens all return the same 404. Prospects are limited to overview, scan, visit and methodology.
- **Webhook is verified and idempotent.** `/hooks/heard-about-us` checks a per-client secret (hashed at rest), requires `submission_id`, handles the concurrent-retry race, and rejects archived clients. `/wa/[token]` only redirects to WhatsApp hosts, checked on both the backend and the frontend.
- **Migrations are clean.** One head. Every `REVOKE ... FROM anon` is guarded. No raw `ALTER TABLE` outside migrations. Early tables get RLS from `344f3422e114`; CI fails if any table lacks it.
- **Frontend/backend types match.** The mechanical diff found no field the frontend reads that the API does not send. The only differences are API fields the frontend ignores (`location_id` on outcome actions, `truth_fact_id` / `truth_fact_version_id` on misinformation findings, `reviewer_note` on truth fact versions, and F-022).
- **Colour functions agree.** `get_score_color` (backend, floors then compares) and `getScoreColor` (frontend, compares raw) give the same colour for every value, including fractions such as 69.6 and 29.9. `SCORE_WEIGHTS` sums to 1.0 and `SCORE_VERSION` is `v1.6.0` as §4 says.
- **Headline counts use scored platforms.** The digest counts, the overtake alert and the competitor head-to-head go through `scored_results`. The digest's "seen X of Y" covers all four question categories while AI Citability covers discovery only; §5 allows this, but the two numbers will not match each other.
- **No scheduled scans exist yet.** There is no scan entry in the beat schedule and `scan_cadence_days` only drives reminders. That matches §1 ("Scans run on demand today"); the §5 guardrails have nothing to apply to.
- **Sender and storage rules hold.** Every sender and footer address is `contact@seenby.my` (the only `hello@` strings are a form placeholder and test fixtures). The digest subject always includes the Growth Readiness score. PDFs go to the private R2 bucket and are served through one-hour presigned URLs; nothing is stored as base64 in Postgres.
- **Scan worker threads are safe.** `_run_platform_queries` reads only attributes that were loaded on the main thread and never touches the session.
- **`sync_remediation_items` is not wrapped in try/except in `run_scan`** but handles and rolls back its own errors, so it cannot flip a completed scan to failed.
- **Raw responses older than 90 days are nulled daily** (`response_text` only). Verbatim quotes copied into `misinformation_findings` and remediation items are kept on purpose and are not covered by the purge.
- **`trustHost: true` and the `/view` prefix check in the middleware** were reviewed and are fine for the current deployment.
- **Stale Supabase references** are limited to the two lines in F-025; the rest are historical notes in migrations and `.env.example` that correctly say production is not Supabase.
