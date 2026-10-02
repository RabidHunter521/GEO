# Google Business Profile Completeness — Implementation Plan

> **For agentic workers:** follow `seenby-phase`. One commit per task, test-first,
> `seenby-verify` per diff. `seenby-migrations` for Task 1,
> `seenby-client-output` for Task 6.

**Goal:** turn the Authority checklist's "Google Business Profile" item from a
manual tick-box into a checked profile: find the client's real Google listing,
check it against the facts on file (name, address, phone, website, hours) and
against what a complete profile has (category, photos, reviews), show each gap
with a plain fix, and prove each fix when it lands.

**Why:** Google AI Overviews, AI Mode and Gemini lean on Business Profile data
for local questions ("best dentist in Bangsar"). Today SeenBy can't see it:
`authority_service.verify_asset` fetches the profile URL, but Google Maps pages
render in the browser, so the check almost never confirms anything, and
ratings/review counts are typed in by hand.

## What exists (verified against master `d2db593`, 2026-10-02)

| Piece | Where | Reused for |
|---|---|---|
| Catalog item `gbp` (review_platform, provenance `google.com`) | `AUTHORITY_ASSET_CATALOG` | the item this upgrades |
| NAP extraction + phone mismatch (last 9 digits) | `authority_service.extract_nap`, `_nap_has_mismatch` | same comparison rules |
| Business locations: address, postcode, phone, website, `hours_json`, `active`, `is_primary` | `models/business_location.py` | the facts to compare against, one listing per location |
| Brand matcher for page text | `brand_detection.detect_brand_mention` | name check |
| Review snapshots (manual) | `authority_service.add_review_snapshot` | unchanged — see decision 2 |
| Work log (admin-published, client-safe) → Progress tab + PDF Authority Progress | `work_log_service`, `report_service._gather_authority_progress` | proof of each fix |
| Brand Authority assisted scoring evidence | `authority_service.summarize_for_assessment` | completeness as evidence, admin still gates the number |
| Cost log + budget | `cost_tracker.record_llm_usage`, `budget_service.check_budget` | every Places call logged |

## Data source

**Google Places API (New)** — official, public listing data (what AI and
buyers see). Text Search to find the listing; Place Details with a field mask
to check it. Pricing (2026): Place Details Enterprise + Atmosphere US$25 / 1,000
with **1,000 free calls a month**; one check is 1–2 calls, so a weekly check of
~100 listings stays inside the free tier.

**Terms constraint:** Google Maps Platform terms let us store a **place ID
indefinitely** but not listing content (name, address, rating, photos) beyond
temporary caching. So we persist only the place ID and **our own pass/fail
results**; the listing's actual values are fetched live when an admin opens the
panel, never stored.

The Places API cannot see some owner-side fields (business description,
posts, Q&A, products/services, review replies). Those become **"check by
hand"** items an admin ticks, kept separate from the automatic ones and never
claimed as verified by SeenBy.

## Design decisions (confirm before Task 1)

1. **Google Places API (New)**, new env var `GOOGLE_PLACES_API_KEY` (a Google
   Cloud key with Places API (New) enabled; the Gemini AI Studio key is a
   different product).
2. **Store place ID + pass/fail only**, per the terms. Rating and review count
   history stays the existing manual snapshot; the panel shows today's live
   rating and count beside it.
3. **One listing per active business location** (clinic chains have several);
   a client with no locations on file uses the client's own name/city/phone.
4. **The admin confirms the match** — SeenBy searches, shows up to 5
   candidates with address, the admin picks one. Never auto-linked: a wrong
   listing would "verify" someone else's business.
5. **Re-checked weekly** (staggered beat task, only confirmed listings) plus
   "Check now". A check flipping fail → pass suggests a work-log entry; nothing
   reaches the client until an admin publishes it.
6. **Client view:** won fixes appear through the work log (Progress tab, PDF
   Authority Progress) — no new client section. Open gaps stay admin-only.

---

## Task 1 — `gbp_listings` model + migration

One row per (client, location — NULL for the client-level listing):
- `place_id`, `confirmed_at`, `confirmed_by_admin_id`
- `checks` JSONB: `[{key, status: pass|fail|unknown, reason_code}]` — our
  results only, no listing content
- `manual_checks` JSONB: `{key: {done: bool, at}}` for the check-by-hand items
- `history` JSONB: `[{date, passed, total}]` (trend of OUR counts)
- `last_checked_at`, `last_check_status` (`ok | not_found | closed | error`)
- unique `(client_id, location_id)` with NULL-safe partial index; FK location
  `ON DELETE CASCADE`; RLS inline; guarded `anon` revoke (CLAUDE.md §8)

Constants: `GBP_CHECKS` (key, label, fix text, automatic|manual), weekly
cadence, photo/review thresholds.

**Done when:** upgrade → downgrade → upgrade on Postgres; RLS gate passes.

## Task 2 — Places client + listing search

**Files:** `services/google_places_client.py` (new), `config.py`,
`cost_tracker.py`, tests with recorded JSON fixtures.

- `search_listings(query, region="my")` → up to 5 candidates
  `{place_id, name, address}` (returned to the admin, not stored).
- `get_listing(place_id)` → field-masked details: `displayName,
  formattedAddress, addressComponents, nationalPhoneNumber,
  internationalPhoneNumber, websiteUri, regularOpeningHours, businessStatus,
  primaryType, types, photos, rating, userRatingCount`.
- Timeout, no SDK retries, one retry on 5xx; `NOT_FOUND` → `not_found`
  (place IDs can expire — the admin re-confirms).
- Each call cost-logged (`google-places-*`, per-request price) and
  budget-checked first.

**Done when:** fixtures for found / closed / not found / quota error map
correctly; missing key → clear "not configured" error, nothing else breaks.

## Task 3 — The checks (deterministic)

**Files:** `services/gbp_service.py` (new), tests.

`run_checks(listing_details, facts) -> list[Check]`, pure and table-tested.
Automatic checks:

| Key | Pass when |
|---|---|
| `operational` | `businessStatus == OPERATIONAL` |
| `name_matches` | `detect_brand_mention(displayName, client/location name)` |
| `category_set` | `primaryType` present |
| `address_matches` | postcode matches the location on file (street tolerated) |
| `phone_matches` | last 9 digits equal (same rule as `_nap_has_mismatch`) |
| `website_matches` | `websiteUri` host = client domain (www/subdomain tolerant) |
| `hours_listed` | `regularOpeningHours` present |
| `hours_match` | equal to `hours_json` when hours are on file, else `unknown` |
| `photos` | ≥ `GBP_MIN_PHOTOS` (5; the API returns at most 10) |
| `reviews` | `userRatingCount ≥ GBP_MIN_REVIEWS` (20) |
| `rating` | `rating ≥ 4.0` |

`unknown` (nothing on file to compare) never counts as a pass or a fail.
Manual checks: description written, products/services listed, posted in the
last 30 days, Q&A answered, replies to recent reviews.

**Done when:** every check has pass / fail / unknown fixtures.

## Task 4 — Link, check, prove

**Files:** `gbp_service.py`, `authority_service.py`, `api/v1/gbp.py` (new,
admin-only), `router.py`, `workers/tasks/maintenance_tasks.py` + beat entry,
tests.

- `POST /clients/{id}/gbp/search` (candidates), `POST …/gbp/listings`
  (confirm a place for a location), `POST …/gbp/listings/{id}/check`,
  `GET …/gbp` (listings + checks + LIVE details fetched on demand),
  `PATCH …/gbp/listings/{id}/manual`.
- A check that finds the listing operational and `name_matches` marks the
  client's `gbp` authority asset **verified** (replacing the page fetch that
  can't read Maps) and sets `nap_mismatch` from `phone_matches`. Creates the
  `gbp` asset if the client hasn't added it yet.
- fail → pass on any check: work-log suggestion, category `authority`,
  source_ref `gbp:{listing_id}:{check_key}`, e.g. "Google Business Profile:
  opening hours now listed". Activity log event registered in all four maps
  + frontend label.
- Weekly beat task: thin, staggered, confirmed listings only, best-effort per
  listing (one failure never stops the batch), respects budget.

**Done when:** tests cover confirm, check → asset verified, flip → one
suggestion (idempotent), not-found → status not_found and no downgrade,
beat isolation.

## Task 5 — Admin UI (Authority page)

**Files:** `src/types/index.ts`, `src/lib/api.ts`,
`components/gbp/*`, `authority/page.tsx`.

A "Google Business Profile" card above the checklist:
- per location: linked listing (or "Find listing" → candidates → confirm),
  completeness `N of M`, each check with pass/fail/unknown and its fix text,
  manual checks as checkboxes, "Check now", last checked, live rating/review
  count, link to the listing on Google Maps.
- shadcn/ui only, admin-only.

**Done when:** typecheck, build, vitest for pure helpers, screenshots with a
fixture-backed listing.

## Task 6 — Evidence + client proof

- `summarize_for_assessment` gains per-listing completeness (counts and
  failing check labels only) so Brand Authority suggestions cite it; the
  admin still gates the number (no `SCORE_VERSION` change).
- PDF Authority Progress already prints published `authority` work-log
  entries; add the `gbp:` prefix to its reader so fixes print as a line.
- Language rules; no listing content, place IDs or check internals on any
  client surface.

**Done when:** PDF rendered and inspected; banned-language scan clean.

## Task 7 — Docs + verify

CLAUDE.md §9 note for the Authority page, architecture map, `.env.example`,
release note (`GOOGLE_PLACES_API_KEY` on `api`, `worker`, `beat`), full
`seenby-verify`, one live search + check from Railway after deploy.

## Out of scope (v1)

Editing the profile for the client (needs the owner's Business Profile API
OAuth); posting updates; review requests (brainstorm #9); Apple Maps / Bing
Places; competitor GBP comparison (natural next step — same checks on a
competitor's listing).

## Risks

| Risk | Mitigation |
|---|---|
| Wrong listing linked | admin confirms every match; candidates show address |
| Storing Google content against the terms | only place ID + our pass/fail persisted; details fetched live |
| Place ID expires | `not_found` status, re-confirm prompt; never downgrades the asset |
| Cost creep | free tier covers ~100 weekly listings; every call cost-logged and budget-checked |
| Flaky Google data read as a regression | a failed check never downgrades `verified`; flips are suggestions an admin publishes |
