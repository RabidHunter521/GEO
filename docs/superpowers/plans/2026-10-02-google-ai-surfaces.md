# Google AI Overviews + AI Mode — Implementation Plan

> **For agentic workers:** follow `seenby-phase`. One commit per task, test-first,
> `seenby-verify` per diff. `seenby-migrations` for Task 2, `seenby-client-output`
> for Tasks 6–7.

**Goal:** scan the two Google surfaces Malaysian buyers actually see — the AI
Overview at the top of a Google search, and Google AI Mode — alongside
ChatGPT, Perplexity, Gemini and Claude, with the same questions, the same
"Seen by AI" detection and the same source capture.

**Why:** most Malaysian buyers search on Google, not in a chatbot. AI Mode
launched in Malaysia in August 2025 (English, then Bahasa Malaysia). Every
serious GEO tool now reports Google's AI surfaces; we report none.

## Verified facts (2026-10-02)

| Fact | Consequence |
|---|---|
| Google has **no official API** for AI Overviews or AI Mode | We buy the data from a SERP-data vendor |
| DataForSEO returns both: `serp/google/organic/live/advanced` (AI Overview item, `load_async_ai_overview=true`) and `serp/google/ai_mode/live/advanced`. Both give answer markdown + `references` (url, domain, title). Pay as you go, no minimum | Recommended vendor |
| Price: organic + async AI Overview ≈ US$0.0012–0.002 per question; AI Mode live US$0.004 | ~28 questions + competitor checks ≈ **US$0.20–0.35 per scan for both surfaces** — far below the LLM platforms |
| An AI Overview **is not shown for every search**; AI Mode always answers | "No AI Overview" must be its own observation, never confused with "Not seen by AI" in text displays |
| Google sued SerpApi over scraping (Dec 2025); the main claims were dismissed July 2026, an amended complaint is pending | Vendor risk: keep the vendor behind one adapter so it can be swapped in a day |
| Platforms are already data-driven: `SCAN_PLATFORMS`, `PLATFORM_LABELS`, per-client `enabled_platforms`, per-platform threads, breakers, cost rows, `platform_breakdown` | Two new platform ids slot into the existing engine; no second scan path |
| 31 backend modules read `brand_detected`; ~20 read `response_text` | A sweep task is needed, scoped to the modules that DISPLAY answer text |

## Design decisions (confirm before Task 1)

1. **Vendor: DataForSEO**, credentials `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`,
   one shared HTTP adapter behind the existing `PlatformClient` protocol.
2. **Two new platforms:** `google_aio` ("Google AI Overviews") and
   `google_ai_mode` ("Google AI Mode"). Malaysia, English, **mobile** device
   (how most Malaysians search). Location/language/device are constants, so BM
   later is a constant plus the multi-locale guardrails (CLAUDE.md §11).
3. **Reported, not yet scored.** Both surfaces appear everywhere results
   appear (scan page, competitors, AI Mirror, win notifications, placements,
   PDF, share view) but are **excluded from AI Citability**, so Growth
   Readiness stays bit-identical and `SCORE_VERSION` is unchanged. After ~4
   weekly scans of real data (appearance rates, stability), adding them to the
   score is a separate change: a `SCORED_PLATFORMS` edit + `SCORE_VERSION`
   v1.5.0 + CLAUDE.md §4, with your sign-off. The existing version
   comparability machinery then labels that score break honestly.
4. **A question with no AI Overview counts as Not seen by AI** in counts (from
   the buyer's side there is no AI answer naming the client), but text
   surfaces show "Google showed no AI Overview for this question", never an
   empty quote. The appearance rate is reported per scan ("Google showed an AI
   Overview for 11 of 28 of your questions").
5. **On for every client by default** (new clients and a one-time backfill),
   switchable off per client in Settings like any platform. Cost is the reason
   it is switchable, not risk — it does not touch the score.

---

## Task 1 — DataForSEO adapter + two platform clients

**Files:** `services/platform_clients/dataforseo.py` (new),
`google_ai_overview.py`, `google_ai_mode.py` (new), `platform_clients/__init__.py`,
`base.py`, `core/config.py`, `core/constants.py`, `cost_tracker.py`, tests with
recorded JSON fixtures.

- `base.PlatformResult` gains `answer_shown: bool | None = None` (None = the
  surface always answers).
- One `_post(endpoint, payload)` with basic auth, the shared
  `PLATFORM_QUERY_TIMEOUT_SECONDS`, no retries of its own (`query_with_retry`
  owns retries and the breaker). Task-level `status_code != 20000` raises.
- AI Overview: organic live advanced, `load_async_ai_overview=true`; find the
  `ai_overview` item; markdown → text (images stripped); `references` →
  `collect_citations`. No item → `PlatformResult(text="", answer_shown=False)`.
- AI Mode: ai_mode live advanced; same mapping; `answer_shown` left None (it always answers, like an LLM platform)
  (an empty AI Mode answer is an error, retried).
- Cost: `model` ids `dataforseo-google-aio` / `dataforseo-google-ai-mode`,
  zero tokens, `search_requests=1`, per-request price in `_SEARCH_COST`.
- Constants: `SCAN_PLATFORMS` + `PLATFORM_LABELS` gain both ids;
  `SCORED_PLATFORMS` = the four LLM platforms; `GOOGLE_SERP_LOCATION_CODE`
  (Malaysia), `GOOGLE_SERP_LANGUAGE="en"`, `GOOGLE_SERP_DEVICE="mobile"`.

**Done when:** fixtures for overview-present, overview-absent, async overview,
AI Mode answer, task error → correct `PlatformResult`; missing credentials →
`PlatformNotConfiguredError` (platform marked unavailable, scan continues).

## Task 2 — Schema: `answer_shown` + default platforms

**Files:** `models/scan_query_result.py`, `models/client.py`, migration,
`scan_service._run_platform_queries` (+ `_attach_sources`), tests.

- `scan_query_results.answer_shown BOOLEAN NULL` (NULL for every existing row
  and for always-answering platforms).
- `clients.enabled_platforms` default and server default gain both ids; data
  migration appends both to every non-archived client's list. Downgrade
  removes them.
- The scan writes `answer_shown` from the result; position extraction is
  skipped when no answer was shown.

**Done when:** upgrade → downgrade → upgrade on Postgres; RLS gate untouched
(no new table); a scan with a mocked absent overview stores one row with
`answer_shown=False`, `brand_detected=False`, zero sources.

## Task 3 — Score stays bit-identical

**Files:** `scoring_service.py`, tests.

- `platform_breakdown` entries gain `scored: bool`, and for `google_aio`
  `answers_shown` (count of questions with an overview).
- `compute_ai_citability` averages only `scored` entries.
- A test pins: same results + two Google platforms → identical AI Citability
  and overall score to the four-platform result.

**Done when:** the pin test passes; existing scoring tests unchanged.

## Task 4 — Sweep: never quote an answer that was not shown

**Files:** one helper `has_answer(result)` in `scan_query_result` (or a small
service), then the text-displaying consumers: `ai_mirror_service`,
`proof_card_service`, `snippet_service`, `misinformation_service` (skip — no
text to check), `query_stability_service` (absent overview is its own
state, not a changed answer), `competitor_intelligence_service`,
`win_loss_service`, `report_service` before/after, `client_view` + `scans`
result schemas (`answer_shown` passes through as a display flag only).

Count-only consumers (score drop alerts, gap matrix, win notifications, digest)
keep counting a missing overview as Not seen by AI — documented, tested once.

**Done when:** each touched consumer has a test with a `answer_shown=False`
row proving it neither quotes nor checks empty text; full suite green.

## Task 5 — Platform-count assumptions

`placement_service.score_target` divides by `len(PLATFORM_LABELS)` (would
silently weaken every breadth score); `ai_mirror_service._PLATFORM_ORDER`;
`methodology_service` platform list; `circuit_breaker`; `alert_service`;
`report_service` platform table. Each decides explicitly: all platforms, or
`SCORED_PLATFORMS`. Placement breadth keeps a fixed denominator so existing
priority scores do not move.

**Done when:** grep shows no `len(PLATFORM_LABELS)` / `len(SCAN_PLATFORMS)`
left implicit; placement ordering pin test unchanged.

## Task 6 — Admin UI

**Files:** `src/types/index.ts` (`Platform` union, `SCAN_PLATFORMS`),
`PlatformIcon`, client create defaults (`clients/actions.ts`), scan page
result rows ("No AI Overview shown" chip), platform breakdown ("Reported — not
yet in the score" note + overview appearance rate), Settings toggles (already
driven by `SCAN_PLATFORMS`).

**Done when:** typecheck, build, vitest; screenshots of the scan page with a
present and an absent overview.

## Task 7 — Client-facing surfaces

Share view Overview / Visibility, monthly PDF platform section, methodology
page:
- Google surfaces listed with their own visibility frequency, marked "Shown
  for reference — not yet part of your score".
- AI Overview appearance rate in plain words.
- Methodology: what each Google surface is, that it is measured through a
  third-party data provider for Malaysia/English/mobile, that not every search
  shows an AI Overview, and that these surfaces do not yet count toward the
  score.
- §2 language rules; no vendor name, request counts or raw payloads on any
  client surface.

**Done when:** PDF rendered and inspected; banned-language scan clean;
share-view schemas whitelist-only (no `answer_shown` leaks beyond a display
flag).

## Task 8 — Docs, release notes, verify

CLAUDE.md §5 (6 platforms, 4 scored), architecture map, `.env.example`,
release runbook note (set the two env vars on `api`, `worker`, `beat` before
deploy — without them both platforms log "unavailable" and the scan proceeds),
full `seenby-verify`, one live smoke query per surface from Railway after
deploy.

## Out of scope (v1)

Bahasa Malaysia / Chinese queries (multi-locale plan); per-city locations;
Bing Copilot, Meta AI (no reliable data source yet); adding Google to the score
(decision 3, later); screenshots of the live SERP.

## Risks

| Risk | Mitigation |
|---|---|
| Vendor blocked or sued out of existence | One adapter; swap vendor without touching the scan engine |
| An AI Overview quoted as empty text, or an absence read as a negative answer | `answer_shown` + Task 4 sweep with tests |
| Score silently changes | `SCORED_PLATFORMS` + pin test (Task 3) |
| Placement priorities shift because "of 4 platforms" became "of 6" | Task 5 fixed denominator + pin test |
| Scan wall time | Google calls run in their own threads like other platforms (~6 s each); well inside the 25-min soft limit |
| Credentials missing in prod | Platform marked unavailable, scan completes (existing behaviour); release note |
