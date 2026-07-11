# Authority & Presence Tracker — Design Spec

**Date:** 2026-07-11
**Status:** Approved design, pending implementation
**Phase:** 4 of the GEO end-to-end roadmap. Standalone, but its best feature
(provenance-driven priorities) reads Share-of-Source data, so ship after Phase 1.

## 1. Goal

Cover the authority-building half of a GEO agency (directories, reviews, social
presence, knowledge-graph readiness, local NAP consistency) as a **tracked, verifiable
checklist per client** — not as automated posting (impossible/ToS-hostile) and not as
bare free-text notes (unverifiable). The differentiator over a generic checklist:
priorities come from SeenBy's own provenance data — *"AI answers in your industry
actually pulled from these domains; you're absent from N of them."*

This also gives Brand Authority assessments (assessment_service) structured evidence
to reason over, and gives the Phase 5 report an "authority actions completed" section.

## 2. Non-goals

- No third-party APIs (Google Reviews, LinkedIn, Trustpilot are all gated). Review
  counts/ratings are admin-entered snapshots or best-effort page reads.
- No automated directory submission. SeenBy tracks and verifies; Faris does the work.
- No score change. Authority assets feed *evidence* into the existing assisted Brand
  Authority flow; the admin still gates the number. No SCORE_VERSION bump.
- No Wikipedia article writing (notability rules). Only a readiness checklist item.

## 3. Data model

New `backend/app/models/authority_asset.py`:

```python
class AuthorityAsset(Base):
    __tablename__ = "authority_assets"
    id              UUID pk
    client_id       UUID fk clients.id CASCADE, index
    asset_key       String(64)      # stable key for catalog items ("gbp", "crunchbase"), null-able free key for custom
    name            String(255)     # "Google Business Profile"
    asset_type      String(32)      # directory | review_platform | social | knowledge_graph | media | other
    url             String(1024) nullable      # the client's profile URL once it exists
    status          String(16) default "missing"   # missing | in_progress | live | verified
    notes           Text nullable                  # admin-only
    provenance_domain String(255) nullable  # domain to match against scan_query_source rows
    review_snapshots JSON default list  # [{date, rating, count}] — review_platform only
    found_nap       JSON nullable       # {name, phone, address_text} extracted at verify time
    nap_mismatch    Boolean default False
    hidden          Boolean default False   # admin archives irrelevant catalog items; history survives
    last_checked_at datetime nullable
    created_at / updated_at
```

One migration, RLS enabled. `(client_id, asset_key)` unique where asset_key not null.

**Client model change:** add `phone: String(64) nullable` (canonical NAP needs it;
city/state/country already exist). Settings page gains the field.

## 4. Default catalog

`AUTHORITY_ASSET_CATALOG` in `core/constants.py` — list of
`{key, name, type, provenance_domain, url_hint}`. Initial set (Malaysia-first, per
target market):

- **directory:** Crunchbase, Clutch, Yellow Pages Malaysia (`yellowpages.my`),
  Malaysia SME directory (`smecorp.gov.my` listing hint), Foursquare/Apple Maps hint
- **review_platform:** Google Business Profile (`google.com` — ONE asset carrying the
  GBP listing status AND its review snapshots), Trustpilot, Facebook page reviews
- **social:** LinkedIn company page, YouTube channel, Facebook page, Instagram
- **knowledge_graph:** Wikidata entity, Wikipedia readiness (checklist only),
  `sameAs` links present in site schema (verifiable from Phase 2's schema.json —
  check works standalone too)
- **media:** industry blog/news mention target (free-slot template)

Catalog rows are **seeded lazily**: first GET of the authority page creates missing
catalog assets for that client as `missing`. Admin can add custom assets and archive
irrelevant ones (soft: status stays, plus a `hidden` boolean — decided: add
`hidden Boolean default False` to the model rather than deleting, so history survives).

## 5. Provenance-driven priorities

New function in `provenance_service` (or a thin `authority_service` helper):
aggregate `scan_query_source` rows for the client's scans → domain → count of
AI answers that used it. Join against assets by `provenance_domain` (suffix match).

The page then shows, per asset: **"Seen in AI sources 12×"** badge, and a
**"Suggested next"** rail: domains with high AI-source counts where the client has no
`live`/`verified` asset — ordered by count. Domains not in the catalog surface as
one-click "Add as target" suggestions. This turns Share-of-Source acquisition targets
into a workable to-do list, which is exactly the §7 "citation gap → close gap" loop
from the agency playbook. Language rule reminder: the UI says "sources AI answers
drew from", never "cited".

## 6. Verification crawler

`authority_service.verify_asset(asset)` — for assets with a URL:

1. `is_safe_crawl_url` + `safe_get` (10s, one URL, no crawling beyond it).
2. Page contains the client name (case-insensitive, normalized whitespace) → status
   `verified`, `last_checked_at` set. Not found → stays `live` with a "couldn't
   confirm automatically" note in the response (many directories render client-side;
   an honest shrug beats a false negative).
3. **NAP extraction (best-effort):** regex phone candidates + client city/name
   occurrences from page text → store in `found_nap`; `nap_mismatch=True` when a
   phone is found that differs (digits-only compare, suffix-match on the last 9
   digits to tolerate country-code formatting) from `client.phone`, or the
   client name differs beyond punctuation. Mismatch renders a warning chip — admin
   judges; nothing automated beyond the flag.

Status lifecycle is otherwise manual: admin moves missing → in_progress → live;
verify button attempts live → verified. Every transition writes ActivityLog
(`authority_status_changed`, note includes asset name + new status) — Phase 5's work
log feeds on these.

**Review snapshots:** on the asset detail, admin enters `{rating, count}`; appended
with today's date to `review_snapshots`. Sparkline trend on the page; the Phase 5
report can say "Google rating 4.2 → 4.5, 31 → 58 reviews". Zero API dependency,
5 seconds of admin time per month per platform. ActivityLog `review_snapshot_added`.

## 7. Brand Authority assessment integration

`build_assessment_prompt(client, "brand_authority")` gains one context block:
counts by status/type plus the verified asset names ("LinkedIn: live, GBP: verified,
Crunchbase: missing, 3 of top 5 AI source domains covered"). Claude's suggested score
gets real evidence; the admin still reviews. No formula/weight change.

## 8. API

`backend/app/api/v1/authority.py`:
- `GET /api/v1/clients/{id}/authority` — assets (seeding on first call) + provenance
  counts + suggested-next rail.
- `POST /api/v1/clients/{id}/authority` — add custom asset.
- `PATCH /api/v1/clients/{id}/authority/{asset_id}` — status, url, notes, hidden.
- `POST /api/v1/clients/{id}/authority/{asset_id}/verify` — crawler check.
- `POST /api/v1/clients/{id}/authority/{asset_id}/review-snapshot` — `{rating, count}`.

Admin-only. Client view: nothing in this phase (Phase 5 decides what surfaces).

## 9. Frontend

New admin page `/clients/[id]/authority` — "Authority & Presence" (CLAUDE.md §9
updated in the same PR):

- **Suggested next** rail on top (provenance-driven, dismissible per item).
- Assets table grouped by type: name, status select, URL field, provenance badge,
  NAP warning chip when flagged, verify button, last-checked.
- Review platforms show the rating/count sparkline + "Add this month's numbers" inline
  form.
- Summary header: "N of M live · K verified · covers X of your top AI source domains".

shadcn/ui, api.ts, types/index.ts as always.

## 10. Error handling

- Verify failures (timeout, SSRF-blocked, non-200) → asset untouched except
  `last_checked_at`; response carries a human "couldn't reach the page" note. Never
  auto-downgrade a status on a failed check.
- Seeding is idempotent (upsert by (client_id, asset_key)); concurrent first-loads
  can't duplicate (unique constraint + on-conflict skip).
- Provenance aggregation failure degrades to the plain checklist (badge-less), never
  a 500 — same isolation philosophy as scan post-commit steps.

## 11. Testing

`test_authority_service.py`:
1. Lazy seeding creates full catalog once; second call adds nothing.
2. Verify: fixture page with client name → verified; without → stays live + note.
3. NAP: fixture with different phone digits → mismatch flag; same digits formatted
   differently ("+60 3-1234 5678" vs "0312345678" style, digits-suffix compare) → no flag.
4. Provenance counts: seeded scan_query_source rows roll up per domain; suggested-next
   excludes covered domains.
5. Review snapshot append + ordering.
6. Status transition writes activity log.
API tests for all five routes; migration up/down (both tables' RLS);
banned-language grep; seenby-verify before merge.

## 12. Build order

1. Migration (authority_assets + client.phone, RLS).
2. Catalog constants + seeding + CRUD service/API + tests.
3. Verify + NAP + review snapshots + tests.
4. Provenance aggregation + suggested-next + tests.
5. Assessment prompt context block.
6. Frontend page + settings phone field + §9 update.
7. seenby-verify + live walkthrough (verify a real GBP/LinkedIn URL).
