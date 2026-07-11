# Page Citability Engine + Content Deliverables — Design Spec

**Date:** 2026-07-11
**Status:** Approved design, pending implementation
**Phase:** 3 of the GEO end-to-end roadmap (depends on nothing from Phase 2; can ship independently)

## 1. Goal

Give SeenBy the content half of a full GEO retainer:

1. **Page citability audit** — score any page on the client's site 0–100 for how
   AI-readable it is (structure, summaries, FAQs, tables, freshness), with concrete
   Claude rewrite suggestions the admin reviews and hands to the client.
2. **Content deliverable generators** — FAQ pack, comparison-page draft, and industry
   glossary, generated from scan evidence (lost queries, win/loss data), admin-reviewed,
   exportable as Markdown. These are the "content production" line items on a
   RM4–5k/month invoice.

Both follow the established assisted pattern: **Claude suggests, the score/verdict is
computed server-side, and the admin gates everything client-facing.**

## 2. Non-goals

- No auto-publishing anywhere, no CMS integration. Output is copy/download only.
- No sitewide crawl — audits are per-URL, admin-initiated, on the client's own domain.
- No Content Quality dimension change. Citability results may inform the admin when
  reviewing a Content Quality assessment, but nothing writes to scores. No
  SCORE_VERSION bump.
- No docx/PDF export in v1 — Markdown covers handoff to any CMS or writer; revisit
  only if a client asks.

## 3. Page citability audit

### 3.1 Service

New `backend/app/services/citability_service.py`.

**Input:** a URL. Validated: same registrable domain as `client.website` (compare via
the `_domain_base` netloc, allowing subdomains), and `url_safety.is_safe_crawl_url`.
Off-domain or unsafe → 422, nothing fetched.

**Fetch + extract:** reuse `content_crawler` conventions (safe_get, timeout, size cap).
Parse with BeautifulSoup; extract main text (`<main>`/`<article>` fallback `<body>`),
headings, paragraphs, tables, lists.

**Deterministic checks** (each `{id, label, status: pass|warn|fail, detail, points}`):

| id | Signal | Points |
|---|---|---|
| `answer_up_front` | First content paragraph ≤ 60 words and appears before any H2 (executive-summary heuristic) | 15 |
| `question_headings` | ≥ 25% of H2/H3s are question-form (starts with what/how/why/when/which/who/can/should/is/are/do/does) | 15 |
| `faq_block` | An "FAQ"/"frequently asked" heading, or ≥ 3 consecutive question headings | 10 |
| `scannable_structure` | ≥ 1 table or ≥ 2 lists (ul/ol) | 10 |
| `paragraph_length` | Median paragraph ≤ 80 words | 10 |
| `heading_density` | ≥ 1 heading per 300 words | 10 |
| `definitions` | ≥ 1 "X is a/an …" definition-pattern sentence in the first half | 5 |
| `freshness_signal` | A parseable date (published/updated) in page text or meta | 10 |
| `author_byline` | Author/byline pattern or `author` meta/JSON-LD | 5 |
| `word_count` | 300–3000 words (thin or bloated both warn) | 10 |

**Score = sum of earned points (0–100), computed in Python.** Claude never produces
the number (same rule as action_center impact). Partial credit: warn earns half points.
Band label via the existing `SCORE_BANDS` names; color via the 3-band traffic light —
both from constants, never hardcoded (CLAUDE.md §3).

**Claude pass (suggestions only):** one call, `max_tokens=1024`, prompt in
`app/prompts/citability.py`. Input: the failed/warned check list + first ~1500 words.
Output JSON: up to 5 items `{"section": str, "issue": str, "rewrite": str}` where
`rewrite` is publish-ready replacement text. Parsed defensively like
`content_brief_service` (failure → audit still saved with empty suggestions and a
retry flag). All strings through `language_sanitizer` — suggestions are handed to
clients verbatim.

### 3.2 Persistence

New model `backend/app/models/page_audit.py`:

```python
class PageAudit(Base):
    __tablename__ = "page_audits"
    id            UUID pk
    client_id     UUID fk clients.id CASCADE, index
    url           String(1024)          # normalized
    score         Integer               # 0–100, server-computed
    checks        JSON                  # list of check dicts
    suggestions   JSON default list     # Claude items, sanitized
    created_at    datetime
```

Re-auditing a URL inserts a new row → per-URL history ("was 45, now 78 after rewrite"
is retainer proof; Phase 5 report reads it). Migration with RLS enabled.

### 3.3 API

`backend/app/api/v1/citability.py`:
- `POST /api/v1/clients/{id}/page-audits` body `{url}` — validate, run, persist, return.
  ActivityLog `page_audit_run`.
- `GET /api/v1/clients/{id}/page-audits` — latest audit per distinct URL (+ previous
  score for delta arrow).
- `GET /api/v1/clients/{id}/page-audits/{audit_id}` — full detail.

## 4. Content deliverable generators

### 4.1 Types and evidence sources

| type | Built from | Output body |
|---|---|---|
| `faq_pack` | Client profile + up to 10 lost/unseen queries from the latest scan (the questions AI is already being asked) | 8–12 Q&A pairs, publish-ready, with a note to also add FAQPage schema (toolkit) |
| `comparison_page` | Client + ONE chosen competitor + win_loss evidence for neutral categories | Factual comparison draft: intro, comparison table, when-to-choose-each, FAQ. Fair-tone rules below |
| `glossary` | Client industry + terms harvested from scan query texts | 15–20 industry terms, one-paragraph plain-English definitions each |

One Claude call per deliverable, `max_tokens=4096`, prompts in
`app/prompts/deliverables.py`. Output is Markdown in a JSON envelope
`{"title": str, "body_md": str}`, parsed defensively, sanitized.

**Comparison-page rules** (baked into the prompt AND spot-checked by sanitizer):
never disparage the competitor, no invented facts/statistics, no superlatives about
the client that aren't in the client profile, and the CLAUDE.md §2 table applies.
This is content published under the client's name — hallucinated claims are a
reputation risk, so the admin-review gate is mandatory, not decorative.

### 4.2 Persistence

New model `backend/app/models/content_deliverable.py`:

```python
class ContentDeliverable(Base):
    __tablename__ = "content_deliverables"
    id             UUID pk
    client_id      UUID fk clients.id CASCADE, index
    type           String(32)            # faq_pack | comparison_page | glossary
    competitor_id  UUID fk nullable      # comparison_page only
    title          String(512)
    body_md        Text
    source_context JSON                  # query ids / evidence used (admin-only)
    status         String(16) default "draft"   # draft | reviewed
    generated_at   datetime
    reviewed_at    datetime nullable
```

`reviewed` is set by an explicit admin action; only reviewed deliverables count as
"delivered" in the Phase 5 report and work log. Regenerating creates a new draft row
(never overwrites a reviewed one). Migration with RLS.

### 4.3 API

`backend/app/api/v1/deliverables.py`:
- `POST /api/v1/clients/{id}/deliverables` body `{type, competitor_id?}` → generate,
  persist draft. ActivityLog `deliverable_generated`.
- `GET /api/v1/clients/{id}/deliverables` — list (newest first).
- `PATCH /api/v1/clients/{id}/deliverables/{did}` body `{body_md?, title?, status?}` —
  admin edits then marks reviewed. ActivityLog `deliverable_reviewed` on the
  draft→reviewed transition.
- `GET .../deliverables/{did}/download` — `text/markdown` attachment.

## 5. Frontend — Content Studio page

New admin page `/clients/[id]/content-studio` (CLAUDE.md §9 gets this line added in
the same PR — the rule is "don't add pages without updating it", so we update it):

- **Page audits** section: URL input + Run, then a table of audited URLs
  (score chip with band color from score-utils, delta arrow, last-audited date);
  row expands to grouped checks + suggestions, each suggestion with a Copy button.
- **Deliverables** section: three generate buttons (comparison opens a competitor
  picker), list of deliverables with status badge, Markdown preview (rendered),
  inline edit, "Mark reviewed", Download.

Content-gaps and content-roadmap pages each get a small link to Content Studio
("Turn these into content →") — no logic change on those pages.

Client view (`/view/[token]/*`) shows nothing from this phase; delivery visibility
arrives with the Phase 5 work log.

## 6. Cost control

Every Claude call through `record_llm_call` with distinct service names
(`citability_suggestions`, `deliverable_faq_pack`, `deliverable_comparison_page`,
`deliverable_glossary`) so cost_tracker/budget_service see them. Deliverable calls are
admin-clicked and infrequent; no new budget category needed.

## 7. Error handling

- URL validation failures → 422 with a human message; nothing persisted.
- Page fetch failure → 502-style service error, nothing persisted (an audit with no
  page behind it is noise).
- Claude failure on suggestions → audit persists with `suggestions: []`; UI offers
  "Retry suggestions", which re-runs the whole audit (we deliberately don't store page
  text, so a retry re-fetches — simpler, and pages rarely change mid-session).
- Claude failure on a deliverable → nothing persisted, retryable error (same contract
  as content_brief_service).

## 8. Testing

`test_citability_service.py`: fixture pages — (1) exemplary page scores ≥ 90;
(2) wall-of-text page fails answer_up_front/paragraph_length/heading_density and
score reflects points table exactly; (3) off-domain URL rejected; (4) Claude failure
→ audit saved, suggestions empty; (5) warn = half points arithmetic.
`test_deliverables.py`: each type generates + persists draft (mock Anthropic);
comparison requires competitor_id; reviewed rows never overwritten by regenerate;
PATCH transitions and activity log rows; banned-language sanitizer applied (inject a
"cited" into the mock response, assert it never lands in body_md).
API + migration tests; seenby-verify before merge.

## 9. Build order

1. Migrations (page_audits, content_deliverables, RLS).
2. citability_service deterministic checks + tests (no Claude yet).
3. Claude suggestions pass + prompts + tests.
4. deliverable service + prompts + tests.
5. API routes + tests.
6. Content Studio page + §9 nav update in CLAUDE.md.
7. seenby-verify + manual walkthrough with one real client page.
