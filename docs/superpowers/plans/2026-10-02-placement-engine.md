# Placement Engine — Implementation Plan

> **For agentic workers:** follow `seenby-phase`. One commit per task, test-first,
> `seenby-verify` per diff. `seenby-migrations` for Task 1, `seenby-prompts` for
> Task 5, `seenby-client-output` for Task 8.

**Goal:** Turn the sources AI answers draw on into a ranked, worked list of
placements: find the third-party pages (listicles, directories, news round-ups)
that AI relies on for the client's buyer questions but that don't name the
client, draft the outreach from approved facts, track each placement through
delivery, and prove the result — first that the page now names the client,
then that the AI answer now sees them.

**Why:** this is the core execution deliverable of an industry-standard GEO
retainer ("4–8 listicles a month", directory work). SeenBy already measures
the gap; this closes it.

## What already exists (verified against master `027ab27`, 2026-10-02)

| Piece | Where | Reused for |
|---|---|---|
| Sources from all 4 platforms per answer, enriched with which brands each page names | `scan_query_sources`, `provenance_service.enrich_scan_sources` | target discovery |
| Acquisition list (client absent, competitor present), flip detection | `provenance_service._summarize`, `_detect_flips` | discovery seed; "placed" detection |
| Per-platform source breakdown | `provenance_service._platform_breakdown` | platform breadth signal |
| Domain category heuristic | `market_intelligence_service.classify_domain_category` | target category |
| Authority checklist (directories, review platforms, social) with `provenance_domain` | `authority_assets`, `authority_service` | link targets to an existing asset instead of duplicating it |
| Delivery lifecycle with due dates, approvals, scan-backed verification | `outcome_actions`, `outcome_action_service`, `outcome_verification_service` | pursuing a placement; proof |
| Home "Action Required" inbox + `/review-queue` driven by Outcome Actions | `home/page.tsx`, `review-queue-buckets.ts` | follow-ups surface for free |
| Approved Truth Vault facts | `pack_query_service.approved_facts_for` | the only facts outreach may use |
| Work log (client-safe, admin-published) + monthly PDF | `work_log_service`, `report_service` | client-facing proof |
| SSRF-safe fetcher | `url_safety.safe_get` | page analysis |

Gaps the plan fills: no per-page record that persists across scans, no ranking
beyond raw count, the acquisition list ignores pages that list *other*
businesses (not tracked competitors) but not the client, nothing analyses a page
or drafts outreach, and nothing links a placement to its proof.

Alembic head: `7c2e9b4d1a60`.

## Design decisions (confirm before Task 1)

1. **Outreach is drafted, never sent by SeenBy (v1).** Admin copies or opens a
   `mailto:`. Sending from SeenBy needs a sending identity per agency,
   deliverability work and consent handling — a later phase if wanted.
2. **Targets include pages that list other businesses, not just tracked
   competitors.** A "Top 10 dentists in KL" page naming ten untracked clinics
   is a prime target; today's acquisition list drops it. Pages naming a tracked
   competitor rank higher.
3. **Clients see won placements only**, through the existing work log and the
   monthly PDF. In-flight outreach stays admin-only.
4. **Lives on the Authority page, not a new route** — "where you are present on
   third-party sites" is exactly that page's job, and CLAUDE.md §9 stays
   unchanged.

---

## Task 1 — `placement_targets` model + migration

**Files:** `models/placement_target.py`, `core/constants.py`, migration
(parent `7c2e9b4d1a60`), `tests/conftest.py` (register model).

One row per (client, canonical URL):
- `url`, `domain`, `title`, `category` (`listicle | directory | news |
  review | social | marketplace | reference | other`)
- `status`: `open | pursuing | placed | verified | stale | dismissed`
- `answers_count`, `platforms` (JSONB list), `query_categories` (JSONB),
  `representative_result_id` (FK `scan_query_results`, SET NULL) — the latest
  answer that drew on the page while the client was not seen
- `competitors_present` (JSONB ids), `other_businesses_listed` (int, from
  analysis), `client_present` (bool, latest enrichment)
- `priority_score`, `priority_reasons` (JSONB)
- `authority_asset_id` (FK, SET NULL), `outcome_action_id` (FK, SET NULL)
- `page_analysis` (JSONB), `analyzed_at`, `outreach_drafts` (JSONB list)
- `first_seen_scan_id`, `last_seen_scan_id`, `last_seen_at`, `placed_at`
- unique `(client_id, url)`; RLS inline; guarded `anon` revoke (CLAUDE.md §8)

Constants: statuses, categories, `PLACEMENT_STALE_AFTER_SCANS = 3`,
category weights (Task 3).

**Done when:** migration upgrade → downgrade → upgrade on Postgres; CI
migrations job (now able to build from empty) passes; RLS gate passes.

## Task 2 — Discovery: refresh targets after every scan

**Files:** `services/placement_service.py` (new), `scan_service.py`
(post-commit hook after the Share-of-Source snapshot), tests.

`refresh_targets(scan_id, client_id, db)` — best-effort, own commit, catch +
rollback + swallow (CLAUDE.md §10):
- From the scan's client-owned answers: third-party sources with
  `fetch_status == "ok"` and the client **not** present → upsert by canonical
  URL. Accumulate answers, platforms, query categories, competitors present;
  set `representative_result_id` to the latest such answer.
- Category: `classify_domain_category`, upgraded to `listicle` when the title
  matches a "best/top N … in …" pattern (deterministic, tested).
- Link `authority_asset_id` when the domain matches an asset's
  `provenance_domain` (directories/review sites already tracked there are
  shown as "tracked in Authority", not duplicated).
- A target whose page now names the client → `client_present = True`; if it
  was `pursuing`, move to `placed` (Task 6).
- Not seen for `PLACEMENT_STALE_AFTER_SCANS` scans → `stale` (kept, never
  deleted; reappearing reopens it).

**Done when:** tests cover new target, accumulation across scans, untracked-
business listicle included, client-present page excluded, authority link,
stale + reopen, failure never undoes the scan.

## Task 3 — Deterministic priority score with reasons

**Files:** `placement_service.py`, tests.

Score (0–100) from stored evidence only, each factor contributing a
human-readable reason:
- answers drawing on the page (log-scaled) and platform breadth
- commercial intent: recommendation/local questions weigh 1.5× brand ones
- competitors present on the page (+), other businesses listed (+)
- category accessibility: directory 1.0, listicle 0.9, news 0.8, other 0.7,
  marketplace 0.5, review 0.4 (worked via the review programme), social 0.4,
  reference 0.3
- recency (last seen this scan vs earlier)

**Done when:** tests pin the ordering on fixtures (a cross-platform listicle
naming two competitors outranks a single-answer social page) and reasons read
correctly. No model call.

## Task 4 — Page analysis (on demand)

**Files:** `placement_service.py`, `api/v1/placements.py` (new, admin-only,
`require_api_key`), `router.py`, tests.

`analyze_target(target)`: one SSRF-safe fetch (+ its linked contact page, max
2 fetches), deterministic extraction:
- listicle structure: numbered headings / list items, count of businesses
  listed, which tracked competitors appear, position of each
- contact paths: `mailto:` links, contact-page URL, "submit / suggest / add
  your business / claim listing" links and forms
- page date (published/modified meta or visible date), author/publisher

Stored on `page_analysis`; contact details are admin-only and never reach a
client surface.

**Done when:** fixture pages (listicle, directory, news, no-contact page)
produce the expected structure; blocked/unsafe URLs fail open.

## Task 5 — Outreach drafts from approved facts only

**Files:** `prompts/placement_outreach.py` (new, via `seenby-prompts`),
`placement_service.py`, tests.

- `directory` targets: deterministic submission checklist (name, address,
  phone, hours, categories, website) filled from approved Truth Vault facts;
  missing facts listed as gaps, never invented.
- Other targets: one Claude call → `{subject, body, ask}` where `ask` is
  `add_to_list | update_listing | correction`. Inputs: page analysis, the
  questions this page answers, competitors listed, client name/site/city, and
  **only** approved facts (`approved_facts_for`). The prompt forbids any claim
  not in the fact list; output passes a check that every number/award/claim
  appears in the supplied facts, else the draft is flagged for edit.
- Cost logged (`record_llm_call`), budget-checked; drafts appended to
  `outreach_drafts` with model + prompt version.

**Done when:** tests with a mocked model cover: facts-only grounding check
rejects an invented award; directory checklist lists gaps; budget exhausted →
no call, clear message.

## Task 6 — Pursue → Outcome Action, with honest proof

**Files:** `placement_service.py`, `outcome_action_service.py` (one source
resolver), `work_log_service.py` (one suggestion), tests.

- **Pursue:** creates an Outcome Action via `suggest_once`
  (`source_kind="placement"`, `source_ref="placement:<target_id>"`,
  `action_type="authority"`, title "Get listed on <domain>",
  `destination_url` = target URL, optional follow-up `due_date`). It then
  appears in the delivery workspace, home inbox and review queue with no UI
  work.
- **Placed** (milestone 1): enrichment finds the client named on the page
  after the action was published → target `placed`, `placed_at`; activity log
  entry; work-log suggestion (category `authority`, client-safe text).
- **Verified** (milestone 2): add `placement:` to
  `source_query_result_for_action`, resolving to the target's
  `representative_result_id`. The existing scan-backed `query_presence`
  verification then marks the action verified only when that same question
  later shows the client Seen by AI. A listing alone never counts as AI
  visibility.

**Done when:** tests cover pursue idempotency, placed only after publication,
verified only via a post-publication scan where the representative question
flips, no_change when it doesn't.

## Task 7 — Admin UI on the Authority page

**Files:** `frontend/src/app/(admin)/clients/[id]/authority/*`, new
`components/placements/*`, `src/lib/api.ts`, `src/types/index.ts`.

"Placement opportunities" section above the checklist:
- ranked table: page (title/domain/category), why (top reasons), platforms,
  competitors listed, status; filters by status/category/platform
- row drawer: questions this page answers, page analysis, contact paths,
  linked authority asset, drafts (generate / edit / copy / open mail),
  Pursue / Dismiss, follow-up date
- shadcn/ui only; admin-only

**Done when:** typecheck + build pass; vitest for any pure ranking/format
helpers; screenshot on the demo client.

## Task 8 — Client-facing proof (won placements only)

**Files:** `report_service.py`, `work_log_service.py`, tests.

- Monthly PDF: "Placements secured" — pages that moved to `placed`/`verified`
  in the period: "Now listed on <domain>, a page AI answers draw on for N of
  your buyer questions." Verified ones add "and the answer now sees you".
- Language rules: "draw on", never "cited"/"mentioned"; numbers come from the
  same target rows (one source for numerator and denominator).
- Nothing about in-flight outreach, contacts or competitors' positions.

**Done when:** render the PDF section and inspect it; banned-language scan
clean; section absent when empty.

## Task 9 — Docs + verify

Methodology note (what "placed" and "verified" mean, and that a listing is not
itself AI visibility), architecture map, full `seenby-verify`, demo-client
walkthrough.

## Out of scope (v1)

Sending email from SeenBy; contact discovery beyond the page and its linked
contact page; scheduled re-analysis; paid placements; review-platform work
(covered by the authority checklist and a future review programme).

## Risks

| Risk | Mitigation |
|---|---|
| Junk targets (navigation pages, login walls) | category weights, `other_businesses_listed`, Dismiss persists across scans |
| Outreach claims something untrue | approved facts only + post-generation grounding check + admin edits before use |
| "Placed" without AI effect read as success | two milestones; only query-presence proof marks the action verified |
| Fetch load | analysis is on demand, max 2 fetches per target; discovery reuses enrichment data, no new fetches |
| Personal contact data | admin-only, page-published business contacts only, never on client surfaces |
