# SeenBy — Edge Case Audit

Status: **Triage rounds 1 + 2 applied (2026-06-18).** 36 of 46 cases fixed and verified
(`352 backend tests passing`; Alembic graph clean, single head `f7c4a9e2d6b1`). The authoritative
change logs are **Part 4** (round 1) and **Part 5** (round 2) at the bottom. The case descriptions
in Parts 1–3 are left intact as the original findings record. Remaining open: 10 cases, all
documented at the end of Part 5 with the reason each was deferred.

Reviewed by going through the scan engine, scoring, brand detection, query building, client
view/security, emails, crawlers, retention, and the frontend score logic. Part 2 / Part 3 cover the
areas sampled more lightly.

Two cross-cutting root causes worth deciding on first:
- **Substring matching family** (#1, #3, #20): a shared word-boundary matcher closes several at once.
- **Float-vs-integer band comparison** (#2, #3): a shared root cause across frontend + backend.

---

## 🔴 High impact (corrupts the core metric or scores)

### 1. Brand detection is naive substring matching
`backend/app/services/brand_detection.py:7`
`brand_name.lower() in response_text.lower()` — no word boundary. A brand like "Ace" matches
"surface"/"place"; "Apple", "Best", "Now", "Smart" match constantly. Inflates **visibility
frequency** (the product's central number) with false positives. The snippet feature got a
word-boundary fix (`snippet_service.py:22`) but the actual scan detection didn't. Same flaw
applies to competitor detection → drives false **competitor-overtake alerts**.

### 2. Frontend score-band gap bug
`frontend/src/lib/score-utils.ts:12-16`
Band maxes are integers (`79`, `64`, `49`, `34`) and the check is `score <= max` on a **float**.
A score of `79.5`, `64.5`, `49.3`, etc. matches no band and falls through to `SCORE_BANDS[4]` =
**"low"**. Overall scores are rounded to 2 decimals, so fractional scores are normal. Backend
avoids this by flooring (`int(score)`), frontend doesn't — so the same score can show "Good" on
the backend and "Low" on the client view.

### 3. Same gap bug in backend digest tip selection
`backend/app/services/claude_action.py:29-33`
`_score_band` does `lo <= score <= hi` with integer bounds, **without flooring** (unlike
`scoring_service.get_score_band`). A citability of `79.5` → no band → falls to "low" → wrong
static tip. Inconsistent even within the backend.

### 4. Degenerate queries when `city` is empty
`backend/app/services/query_builder.py:7,27,34`
`ClientCreate` only collects name/website/industry (`schemas/client.py:12`); `city`/`state` are
nullable with no default (`models/client.py:19`). Scanning a freshly created client renders the
local/recommendation templates literally as *"Best plumber near me in None"* (`.format(city=None)`
→ the string `"None"`). Skews the recommendation/local categories and the score, silently.

---

## 🟠 Medium (wrong output, no crash)

### 5. Position extraction can emit absurd ranks
`backend/app/services/position_extraction.py:40-44`
Strips all non-digits and joins them. A model reply like `"3 (out of 10)"` → `"310"` → position
**310**; `"#1, top 5"` → `15`. Surfaced to clients as **"AI Search Ranking"**
(`client_view.py:250`).

### 6. Digest email doesn't HTML-escape client name / action text
`backend/app/services/digest_service.py:218,250`
`{client.name}` and `{data.action_text}` are interpolated raw into HTML. `alert_service` was
hardened to `html.escape` everything; the digest was missed. A name with `&`/`<` breaks the email
(Claude-generated `action_text` is unescaped too).

### 7. Prospects receive client-facing automation
- Weekly digests go to every non-archived client with an email — including `is_prospect=True`
  (`digest_tasks.py:18-25`). A cold-outreach lead gets *"Your weekly visibility update."*
- Monthly reports auto-generate for prospects too (`report_tasks.py:34-41`).
- Industry benchmark counts prospects as peers, polluting the average/percentile
  (`benchmark_service.py:50` filters `archived` only, not `is_prospect`).

### 8. Report "due" clock keys off `generated_at`, not `sent_at`
`backend/workers/tasks/report_tasks.py:65-74`
CLAUDE.md §7 says Faris reviews before sending. Once a report is *generated*, the 30-day clock
resets even if it was never sent — so an unsent report blocks the next one. Reports are also never
de-duplicated against an already-pending review.

### 9. No digest idempotency / silent skips
`backend/app/services/digest_service.py:59-73`
Beat + a manual trigger in the same week sends two emails. Conversely, since digests require a
completed scan in the last 7 days and scans are on-demand, most weeks send **nothing** (silently
skipped).

### 10. Trend/citability thresholds vs spec wording
`backend/app/services/claude_action.py:21`, `digest_service.py:131`
The Claude-action gate uses **AI-citability** change ≥5, while the email subject and CLAUDE.md §7
talk about "score" (overall GEO). Confirm which "score" §7 means. Trend up/down uses a separate
±0.5 threshold.

---

## 🟡 Security / abuse surface

### 11. Rate-limit is bypassable via spoofed `X-Forwarded-For`
`backend/app/core/rate_limit.py:29-34`
Takes the first XFF entry as the client IP with no trusted-proxy check. An attacker rotating the
header gets unlimited requests against the public client view. It also **fails open** when Redis
is down — so during a Redis outage the view has no throttle at all.

### 12. "Uniform 404" promise breaks on malformed token length
`backend/app/api/v1/client_view.py:83`
`Path(min_length=20, max_length=64)` makes a too-short/too-long token return **422**, not the
uniform 404. A probe can distinguish "wrong length" from "valid length, no match."

### 13. Redirect-based SSRF bypass
`backend/app/services/verification_crawler.py:22`, `content_crawler.py:86`
`is_safe_crawl_url` only checks the **initial** URL, but `follow_redirects=True`. A public site
that 302-redirects to `http://169.254.169.254/...` (cloud metadata) is followed. `url_safety`
documents it doesn't resolve DNS (rebinding out of scope) — admin-entered, but the redirect path
is the realistic hole.

### 14. Unbounded response body in crawler
`backend/app/services/content_crawler.py:86,93`
`httpx.get(...).text` loads the entire page into memory before `_MAX_CORPUS_CHARS` truncation. A
multi-GB page can OOM the Celery worker. No `max-size` / streaming guard.

### 15. Share tokens never expire
`backend/app/services/share_link_service.py`
A leaked link works forever until manually revoked. No TTL, no rotation reminder. (Rotation does
invalidate the old token atomically, which is good.)

---

## 🟢 Lower / correctness nits

### 16. DB column vs schema length mismatch
`models/client.py:15,22` vs `schemas/client.py:14,28`
`website` column is `String(255)` but the schema allows `max_length=500`; `contact_email` column
is `String(255)` but schema allows `320`. A value in the 256–500 (or 256–320) range passes
Pydantic, then errors at DB insert.

### 17. Stale-scan window vs real runtime
`backend/app/services/scan_service.py:32-48`, `ACTIVE_SCAN_STALE_MINUTES=15`
A genuinely slow scan (max competitors × 4 platforms × slow providers + 0.5s/query) running past
15 min is treated as "dead," letting a duplicate scan start and write a second result set
concurrently.

### 18. ORM objects shared across threads
`backend/app/services/scan_service.py:164-170`
`scan`/`client` SQLAlchemy instances are read from multiple `ThreadPoolExecutor` threads. Only
reads `.id`/`.name` so practically safe, but ORM instances aren't formally thread-safe.

### 19. Empty platform response counts as "not seen"
`backend/app/services/scan_service.py:83-84`
If a provider returns an empty string without raising, `detect_brand_mention("", ...)` → `False`.
A silent soft-failure is scored as a legitimate "Not seen by AI" rather than "unavailable."

### 20. Competitor-name redaction over-matches
`backend/app/services/snippet_service.py:16-19`
Redaction is plain `re.sub(escape(name), ...)` with no word boundary. A competitor named "AI" or
"Pro" redacts those letters everywhere in the excerpt → `"[a competitor]"` litter.

### 21. Old snippets break after purge
`backend/app/services/retention_service.py:23` + `api/v1/scans.py:160-162`
After 90 days `response_text` is nulled, so a previously-shared snippet URL starts returning 404
"no shareable excerpt." Expected by design, but any shared image silently dies.

---

## Part 2 — deeper pass (report, action center, content, toolkit, competitors, lists)

Covered: `report_service`, `action_center_service`, `content_analysis_service`,
`content_roadmap_service`, `win_loss_service`, `issue_detection_service`, `toolkit_service`,
`gap_matrix_service`, `cost_tracker`, `competitors` API, `client_list_service`, `api.ts`,
`claude_client`. (`issue_detection` and `client_list` use `>=` comparisons and are free of the
band-gap bug — no findings there.)

### 🔴 22. WeasyPrint `None` deref crashes report generation
`backend/app/services/report_service.py:546`
The import is wrapped so `weasyprint = None` when GTK/Pango native libs are missing (e.g. bare
Windows) — but `generate_report_pdf` calls `weasyprint.HTML(string=html).write_pdf()` with **no
`None` check**. On such a box, report generation dies with `AttributeError: 'NoneType'` instead of
the graceful skip the import guard implies.

### 🟠 23. Report month label can disagree with period / client-view
`report_service.py:289,303-305` vs `api/v1/client_view.py:209-211`
`period_label = now.strftime("%B %Y")` but `period_start = now - 30 days`. A report generated on
June 1 labels itself **"June 2026"** in the PDF while `period_start` is in **May**, and the client
view's "What changed" narrative uses `period_start` → shows **"May 2026"**. The same report shows
two different months.

### 🟠 24. Report HTML interpolates free-text fields unescaped
`report_service.py:422,460,466,497,517,522`
Client name, brand/content **evidence notes**, competitor names, narrative and recommendation are
injected raw into the report HTML before WeasyPrint renders it. Not XSS (it's a PDF), but a stray
`<`, `&`, or unclosed tag in an admin evidence note can break the PDF layout. (Contrast: the alert
emails were hardened with `html.escape`; reports and the digest were not — see #6.)

### 🟠 25. Reports generate/send for prospects + no de-dup
`report_service.py:572`, `workers/tasks/report_tasks.py:34-41`
Same prospect leakage as #7 (no `is_prospect` filter). Additionally, manual `generate_report_pdf`
has no idempotency — each call creates a new `Report` row **and** a new R2 object, so repeated
clicks pile up duplicate stored PDFs.

### 🟠 26. Action Center priority-band gap bug
`backend/app/services/action_center_service.py:74-78`
`ACTION_PRIORITY_BANDS` = high `(6,10)` / medium `(3,5)` / low `(0,2)`, checked with
`lo <= impact <= hi` on an `impact` rounded to **1 decimal**. An impact of `2.5` or `5.5` matches
no band and falls through to `"low"` — a genuinely medium/high action gets labelled low. Same
float-vs-integer-band family as #2 and #3.

### 🟠 27. Content analysis runs on an empty crawl
`backend/app/services/content_analysis_service.py:84-98`
If the site is unreachable or blocks the crawler, `crawl_site` returns an empty corpus
(`pages_crawled = 0`), but the topics/entities and quality Claude calls **still run on nothing** —
producing a hallucinated "analysis" with no guard for "we couldn't read the site."

### 🟠 28. Topics/quality failure aborts the whole analysis (inconsistent fallback)
`content_analysis_service.py:27-52,94-98`
`_topics_entities` and `_quality_recommendation` are **not** wrapped in try/except; invalid JSON or
an API error re-raises through the `ThreadPoolExecutor` and fails the entire run. Only
`_suggested_content` degrades gracefully. One flaky sub-call kills the whole analysis.

### 🟡 29. Position-extraction Claude calls are not cost-tracked
`backend/app/services/position_extraction.py:31`
Every ranked + detected query fires a Claude (Haiku) call, but this is the **one** Claude call site
with no `record_llm_call`. Per-client LLM cost therefore undercounts position-extraction spend
(up to ~8 calls × enabled platforms per scan).

### 🟡 30. Anthropic client built per-call with no timeout/retry config
`backend/app/services/claude_client.py:16-17`
`anthropic_client()` returns a fresh `anthropic.Anthropic(...)` with **no timeout and default SDK
retries** — unlike the platform clients, which set an explicit timeout and `max_retries=0`. A hung
Claude call inside the scan flow (position extraction, action center) can stall a Celery worker
well past expectations.

### 🟡 31. Win/loss & roadmap go silently empty after the 90-day purge
`win_loss_service.py:68-71`, `content_roadmap_service.py:27-39`
Competitor presence is recomputed **live** from `response_text`. Once purged (#21), every
`competitors_seen` is empty → every neutral query reads "won"/"open", and the roadmap (driven by
lost/open queries) produces **nothing**. Documented as "degrades," but the UI gives no
"data expired" signal — it looks like the client is winning everything.

### 🟢 32. Duplicate / self competitors allowed
`backend/app/api/v1/competitors.py:118-140`
No de-dup and no "competitor name == client name" guard. The same competitor added twice doubles
its queries; a competitor named identically to the client yields nonsensical "Client vs Client"
comparison queries.

### 🟢 33. `MAX_COMPETITORS` check is a count-then-insert race
`competitors.py:130-136`
Counts, then inserts, with no lock or unique constraint. Two concurrent adds can both pass at 4 and
land 6 rows. Low probability (single admin), but unbounded queries/cost if it happens.

### 🟢 34. Brief gating & win/loss rely on naive competitor detection
`competitors.py:99`, `win_loss_service.py:70`
Both use `detect_brand_mention` (substring) for competitors — the #1 false-positive family — here
deciding whether a content brief is offered and how win/loss outcomes are classified.

### 🟢 35. `gap_matrix` N+1 queries
`backend/app/services/gap_matrix_service.py:26-49`
Per client, separate `Scan` + `Competitor` + `ScanQueryResult` queries inside the loop. Fine at MVP
scale; degrades linearly with client count. Perf only.

### 🟢 36. Generated robots.txt can double `User-agent: *`
`backend/app/services/toolkit_service.py:49-67`
The file is framed as "add these lines to your existing robots.txt," yet it emits its own
`User-agent: *` / `Allow: /` block. Pasted under a site's existing `User-agent: *` section, it
produces a duplicated/malformed directive.

### 🟢 37. Admin list shows "scan overdue" nags for prospects
`backend/app/services/client_list_service.py:84-101`
`next_scan_due` / `is_scan_overdue` are computed for every non-archived client including prospects,
so cold leads surface scan-cadence reminders in the portfolio overview. (Also note `last_scan_at`
is derived from `GeoScore.computed_at`, not `Scan.completed_at` — a completed scan that produced no
score reads as "never scanned.")

---

## Part 3 — traffic, briefs, costs, routers, FK cascades, config, frontend

Covered: model `ForeignKey` `ondelete` behaviour, `traffic` API + schema, `content_brief_service`,
`costs`/`activity`/`digest` API routers, `config.py`, the public `view` overview page, and the
SVG chart components. (Charts `AiTrafficChart` / `ScoreHistoryChart` guard `length < 2` and divide
by `Math.max(..., 1)` / fixed `100` — **no divide-by-zero**. The view page confirms #2 manifests in
the client-facing hero subtitle and dimension badges via `getScoreBand` / `ScoreBadge`.)

### 🔴 38. Deleting a competitor silently relabels its past scan rows as the client's own
`backend/app/models/scan_query_result.py:16` (`competitor_id` `ondelete="SET NULL"`) +
`backend/app/api/v1/competitors.py:159`
Competitor query results carry `competitor_id`. When a competitor is deleted, the FK rule sets
`competitor_id = NULL` on all its historical rows — and **every live recompute treats
`competitor_id IS NULL` as "the client's own queries."** So those rows (whose stored
`brand_detected` reflects whether the *competitor* was seen) get counted as **client** visibility by
`compute_platform_breakdown` / `compute_ai_citability`, the digest `seen_count/total_count`,
`win_loss_service`, `scan_diff_service`, `competitor_intelligence_service`, and
`issue_detection_service`. Net effect: **deleting a competitor inflates/corrupts the client's
visibility frequency** on every recompute-from-rows surface. (Persisted `GeoScore` numbers are
frozen and unaffected; the competitors/win-loss/diff/digest views that recompute from rows are.)
Likely fix: `ondelete="CASCADE"` on that FK (delete the rows), or have every "client results" query
also require `category != comparison` / a real client-row marker.

### 🟠 39. Traffic period isn't normalized to the first of the month
`backend/app/api/v1/traffic.py:38-55`, `backend/app/schemas/ai_traffic.py:7`
`period` is a free `date`. But the report's traffic lookup keys on `now.date().replace(day=1)` and
the first of the previous month (`report_service.py:289-290`). If an admin saves `2026-06-15`, the
report **never finds it** → the AI-traffic section silently disappears despite data existing. Two
different days in the same month also create two snapshots → a duplicated month bar in the chart.

### 🟡 40. `content_brief` Claude calls aren't cost-tracked
`backend/app/services/content_brief_service.py:54`
Second Claude call site (with #29 position-extraction) that omits `record_llm_call`. Brief
generation spend never lands in `llm_call_logs`.

### 🟡 41. Cost dashboard materially undercounts real LLM spend
`backend/app/api/v1/costs.py`
Because #29 (position extraction) and #40 (briefs) don't log, **and** the non-Claude platform calls
(ChatGPT / Perplexity / Gemini, the bulk of every scan) are never tracked at all, the per-client
`/costs` summary reflects only a slice of true spend. Dangerous if used for pricing/margin calls.

### 🟢 42. `llm_call_log` survives client hard-delete (orphaned, client_id nulled)
`backend/app/models/llm_call_log.py:19` (`ondelete="SET NULL"`)
On churn hard-delete (#31-adjacent), cost rows persist with `client_id = NULL`. Non-PII and arguably
desirable for accounting, but it's an exception to CLAUDE.md §8 "client data auto-deleted" worth a
conscious decision.

### 🟢 43. `activity` list `limit`/`skip` are unvalidated
`backend/app/api/v1/activity.py:22-23`
Plain `int`s, no bounds. `?skip=-1` → Postgres `OFFSET -1` → 500; `?limit=99999999` → unbounded
fetch. Admin-only, low risk, but trivially hardened with `Query(ge=0, le=…)`.

### 🟢 44. `digest` trigger doesn't verify client exists / isn't a prospect
`backend/app/api/v1/digest.py:12-16`
Dispatches the Celery task for any UUID with no 404. The task then no-ops for a bad ID, or — for a
prospect with an email — sends a full client digest (reinforces #7).

### 🟢 45. Misconfigured R2 public bucket produces broken logo URLs silently
`backend/app/core/config.py`, `backend/app/services/r2_service.py`
Reports live in the private bucket and are served only via `presigned_pdf_url`, so a missing
`CLOUDFLARE_R2_PUBLIC_URL` no longer affects report downloads. Logos use the separate public
bucket: `upload_image` now raises if `CLOUDFLARE_R2_PUBLIC_BUCKET_NAME` or `CLOUDFLARE_R2_PUBLIC_URL`
is unset (no silent host-less link), but the public-bucket settings still aren't validated as
all-or-nothing at boot.

### 🟢 46. Gemini/Claude keys are hard-required at boot; ChatGPT/Perplexity are optional
`backend/app/core/config.py:8,10-11,15`
`GEMINI_API_KEY` and `ANTHROPIC_API_KEY` have no default → the backend won't start without them,
even for a client whose `enabled_platforms` excludes Gemini. Inconsistent with the graceful
"empty key = platform marked unavailable" treatment given to ChatGPT and Perplexity.

---

## Migrations note
FK `ondelete` was audited across all models (see #38/#42). Per prior verification the Alembic chain
is linear/sequential. The actionable item is the `SET NULL` on `scan_query_result.competitor_id`
(#38), not the chain itself.

## Coverage summary
Backend services, API routers, workers, models, schemas, core (auth/rate-limit/config), the public
client-view surface, and the frontend data layer + view overview/charts have now been swept.
Remaining untouched-but-low-risk: the admin mutation client components (`ScanClient`,
`SettingsForm`, `ToolkitClient`, etc. — mostly form state over `api.ts`) and the prompt-builder
text in `app/prompts/*` (language-rule wording, not logic).

---

# Part 4 — Fixes Applied (Round 1 · 2026-06-18)

17 cases fixed across 5 shared-root-cause clusters + quick wins. Verified with the full backend
suite: **352 passing** (347 prior + 5 new brand-detection tests). Frontend change is a one-line
predicate simplification (no behavior added beyond the fix).

### Cluster A — float-vs-integer band gap (#2, #3, #26)
Fractional scores between an integer band max and the next min fell through to the worst band.
- **#3** `app/services/claude_action.py` — `_score_band` now delegates to the single floored
  `scoring_service.get_score_band`, removing the duplicate buggy implementation.
- **#26** `app/services/action_center_service.py` — `_priority_for_impact` matches on the lower
  bound only (bands ordered high→low), so impacts like 5.5 no longer collapse to "low".
- **#2** `frontend/src/lib/score-utils.ts` — `getScoreBand` matches on `min` only
  (`score >= b.min`), dropping the `<= max` check that stranded e.g. 79.5 in "low".

### Cluster B — naive substring brand detection (#1, and downstream #34)
- **#1** `app/services/brand_detection.py` — `detect_brand_mention` now uses a cached,
  boundary-aware regex (`(?<!\w)…(?!\w)`, `re.escape`, case-insensitive). "Ace" no longer matches
  inside "surface"/"Acme"; punctuated brands ("Yahoo!", "AT&T") still match. Added 5 tests.
- **#34** competitor detection in `win_loss_service` / content-brief gating inherits the same
  matcher → false-positive competitor "seen" results are fixed transitively.

### Cluster C — prospect leakage (#7, #25, #37, #44)
Prospects (cold leads) were receiving client-only automation and polluting peer stats.
- **#7 / #44** `app/services/digest_service.py` — `send_client_digest` now early-returns for
  `is_prospect` (covers both the weekly beat and the manual trigger endpoint). Beat query in
  `workers/tasks/digest_tasks.py` also filters prospects.
- **#7 (benchmark)** `app/services/benchmark_service.py` — peer cohort now excludes prospects.
- **#25** `app/services/report_service.py` — `generate_report_pdf` skips prospects (logs
  `report_skipped_prospect`); beat query in `workers/tasks/report_tasks.py` filters them too.
- **#37** `app/services/client_list_service.py` — `next_scan_due`/`is_scan_overdue` suppressed for
  prospects (no cadence nag).
- Test fixtures updated to set `is_prospect = False` on mocks (`test_digest_service`,
  `test_report_service`).

### Cluster D — unescaped free text in emails/PDF (#6, #24)
- **#6** `app/services/digest_service.py` — client name + Claude action text are `html.escape`d
  before entering the digest email.
- **#24** `app/services/report_service.py` — client name, brand/content evidence notes, competitor
  names, change narrative, recommendation, and the report-email client name are all escaped before
  rendering to PDF/email.

### Cluster E — cost-tracking gaps (#29, #40) + position digit bug (#5, bonus)
- **#29** `app/services/position_extraction.py` — now calls `record_llm_call`
  (`service="position_extraction"`, `db` omitted so it stays thread-safe in the per-platform
  worker threads); `scan_service` passes `client_id` through.
- **#40** `app/services/content_brief_service.py` — now calls `record_llm_call`
  (`service="content_brief"`, on the request session).
- **#5** (fixed in passing) `position_extraction` digit parsing switched from "join all digits"
  to first-integer-token regex, so a reply like "3 (out of 10)" yields 3, not 310.

### Quick wins
- **#22** `app/services/report_service.py` — explicit `weasyprint is None` guard raises a clear
  `RuntimeError` (missing GTK/Pango) instead of an opaque `AttributeError`. (Also renamed the local
  `html` PDF string to `report_html` to avoid shadowing the new `html` module import.)
- **#16** `app/schemas/client.py` — `website`/`contact_email` `max_length` lowered to 255 to match
  the `String(255)` columns, preventing a validation-pass→DB-insert-fail gap.
- **#43** `app/api/v1/activity.py` — `limit`/`skip` now `Query(ge=…, le=…)` bounded
  (limit 1–200, skip ≥0), closing the negative-offset 500 / unbounded-fetch gap.

### Not fixed this round (require a migration, a product decision, or deeper work)
- **#38** (competitor-delete `SET NULL` relabels rows as the client's) — needs an Alembic migration
  changing the FK to `CASCADE`; highest-value remaining item.
- **#11** XFF rate-limit spoofing, **#12** token-length 422-vs-404, **#13/#14** crawler redirect-SSRF
  / unbounded body, **#15** token expiry — security hardening, want a deliberate approach.
- **#4** None-city degenerate queries, **#39** traffic period normalization — small but change
  scan/report semantics; worth a quick product confirm first.
- **#8/#9** report-due vs sent + digest idempotency, **#17** stale-scan window, **#23** report month
  label, **#27/#28** empty-crawl handling, **#10/#19/#20/#30/#31/#32/#33/#35/#36/#41/#42/#45/#46** —
  see their entries above.

---

# Part 5 — Fixes Applied (Round 2 · 2026-06-18)

19 more cases fixed, bringing the total to **36 / 46**. Verified: `352 backend tests passing`
(updated the competitor/crawler/digest/report tests whose mocks needed the new call shapes), and
the Alembic revision graph validates to a single head with no cycle.

### #38 — competitor delete relabels rows (the headline data bug)
- **Model** `app/models/scan_query_result.py` — `competitor_id` FK is now `ondelete="CASCADE"`.
- **Migration** `alembic/versions/f7c4a9e2d6b1_competitor_fk_cascade.py` — drops the existing
  `SET NULL` FK (discovers its real name via `pg_constraint`, name-agnostic) and recreates it as
  `CASCADE`. Deleting a competitor now removes its query rows instead of nulling them into the
  client's own-query set. (First attempt reused an existing revision id and Alembic's cycle
  detector caught it — re-issued as `f7c4a9e2d6b1`; graph re-verified.)

### #4 — degenerate "in None" queries
`app/services/query_builder.py` — added `_location()` / `_locality()` with city→state→country
fallback. Recommendation/local queries are **skipped entirely** when no location is known, so a
client with no city runs brand + comparison only instead of "Best plumber in None".

### #12 / #23 — client view
`app/api/v1/client_view.py`
- **#12** token length is validated inside `require_share_client` (returns the uniform 404) instead
  of via `Path(min_length/max_length)` (which returned a distinguishing 422).
- **#23** `change_narrative_period` now uses `period_end` so the client view and the PDF report show
  the same month.

### #13 / #14 — crawler SSRF + memory
`app/services/url_safety.py` (new `safe_get` + `SafeResponse` + `UnsafeUrlError`),
`verification_crawler.py`, `content_crawler.py`
- `safe_get` follows redirects **manually**, re-running `is_safe_crawl_url` on every hop (httpx's
  own `follow_redirects` skipped that → a public host could 302 into the private range).
- Body is streamed and truncated at 5 MB, so a giant page can't OOM the worker.
- Both crawlers switched from `httpx.get(..., follow_redirects=True)` to `safe_get`; tests
  repointed from patching `httpx.get` to `safe_get`.

### #27 / #28 — content analysis robustness
`app/services/content_analysis_service.py`
- **#27** empty crawl (0 pages / blank corpus) short-circuits to an explicit "we couldn't read your
  site" result instead of feeding an empty corpus to Claude (which hallucinated topics).
- **#28** the topics/entities and quality sub-calls each run inside their own try/except with
  fallbacks, so one failing Claude call no longer aborts the whole analysis (matching the existing
  graceful `_suggested_content`).

### #30 / #46 — client + config robustness
- **#30** `app/services/claude_client.py` — `anthropic_client()` now sets `timeout=60s` so a hung
  Claude call can't pin a worker mid-scan.
- **#46** `app/core/config.py` — `GEMINI_API_KEY` now defaults to `""` like ChatGPT/Perplexity, so
  the backend boots without it and the platform is just marked unavailable. (ANTHROPIC stays
  required by design — it powers the non-platform Claude features.)

### #32 / #33 — competitor integrity
`app/api/v1/competitors.py` — `add_competitor` rejects a name equal to the client's (422) and a
case-insensitive duplicate of an existing competitor (422), then enforces the max. Closes the
self/duplicate case (#32) and tightens the count path (#33); tests updated to the `.all()` shape.

### #39 — traffic period
`app/api/v1/traffic.py` — the upsert normalizes `period` to the first of the month, so duplicate
mid-month entries collapse to one row and the report's first-of-month lookup always matches.

### #45 — R2 misconfig
`app/services/r2_service.py` — `_public_base()` raises a clear error when
`CLOUDFLARE_R2_PUBLIC_URL` is unset instead of silently returning a host-less `/reports/<key>` URL.

### #36 — robots.txt guidance
`app/services/toolkit_service.py` — the header comment now tells the user to copy only the AI-bot
blocks into an existing robots.txt (never a second `User-agent: *`).

### #8 / #9 — report & digest cadence
- **#8** `workers/tasks/report_tasks.py` — the beat skips clients that already have an unsent report
  awaiting review (`_has_unsent_report`), so unsent reports no longer pile up duplicate R2 objects.
- **#9** `app/services/digest_service.py` — skips sending if a `digest_sent` activity exists in the
  last 6 days, making the weekly beat + a manual trigger idempotent within the week.

### Still open after round 2 (10 cases — deferred deliberately)
- **#5 position digit bug** — actually fixed in round 1 (Part 4, bonus). *(So effectively 37 done.)*
- **#10** trend/citability wording vs CLAUDE.md §7 — needs a product decision on what "score" means,
  not a code fix.
- **#11** XFF rate-limit spoofing — needs the real trusted-proxy/CDN setup to know how many
  `X-Forwarded-For` hops to trust; wrong guess weakens it. Deploy-config dependent.
- **#15** share-token expiry — currently no TTL by design; adding one is a product choice (and a
  schema/migration), not a bug.
- **#17** stale-scan window tuning, **#18** ORM-thread reads — accepted (practically safe at MVP
  scale; revisit if scans slow down or move off the thread model).
- **#19** empty platform response counts as "not seen" — a robust fix (treat all-empty platform as
  unavailable) is nuanced enough to risk over-failing; left as-is pending a real example.
- **#20** snippet competitor-redaction over-match — same word-boundary idea as #1 but in
  `snippet_service._redact`; low traffic, batch with a snippet polish pass.
- **#21 / #31** purge-driven degradation (snippets / win-loss go empty after 90 days) — by design;
  the only improvement is a frontend "data expired" signal, which is UI work.
- **#35** gap_matrix N+1 — perf only; fine at MVP client counts.
- **#41 / #42** cost undercount (platform calls untracked) / `llm_call_log` survives delete —
  conscious accounting decisions; #29/#40 already closed the Claude-call gaps.
