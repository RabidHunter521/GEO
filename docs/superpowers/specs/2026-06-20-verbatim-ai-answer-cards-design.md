# Verbatim AI Answer Cards — Design

**Date:** 2026-06-20
**Status:** Approved (design), pending implementation plan
**Owner:** Faris

## Problem

The client view tells clients they're "seen by AI in 12 of 20 questions" but never
*shows* them the actual AI answer. The single most visceral, premium-justifying
artifact in AI-visibility tracking is the verbatim answer itself:

> "A buyer asked ChatGPT 'best dental clinic in KL' — here's the actual answer.
> You're named in paragraph one." (win)
>
> "ChatGPT recommended a competitor — you weren't mentioned." (loss)

This is what a client screenshots and forwards to their boss. It is the strongest
recurring justification for the RM4200/month price.

## Key finding — most of this already exists

- `ScanQueryResult.response_text` stores the full verbatim AI answer per query.
- `app/services/snippet_service.py` already extracts the brand sentence, redacts
  competitor names to `[a competitor]` (word-boundary, case-insensitive), and
  renders a 1200×630 PNG with a "Tracked by SeenBy" watermark.
- An admin-only endpoint exists: `GET /api/v1/scans/{scan_id}/results/{result_id}/snippet.png`
  (401 without API key). The client-facing token-gated view shows **zero** verbatim text.

This feature **surfaces the proven, already-compliant capability** into the read-only
client view as live HTML cards. It is a surfacing + one-new-function task, not a
from-scratch build.

## Decisions

- **Scope:** wins **and** losses. (Not hallucinations in this iteration.)
- **Placement:** hero proof on the overview page + inline expandable on each scan row.
- **Render format:** live HTML text cards (accessible, selectable, responsive, SEO-safe).
  The existing admin PNG export stays unchanged for sharing.
- **Architecture (Approach A):** compute server-side in the client-view API. The public
  surface only ever receives `{kind, platform_label, category, excerpt}`. `response_text`
  never leaves the server.

### Rejected approaches

- **B — extract client-side:** would ship full `response_text` to a public token-gated
  page. Direct violation of CLAUDE.md §8. Rejected.
- **C — precompute & persist cards at scan time:** schema change + Alembic migration, and
  cards go stale when the competitor list changes (redaction depends on it). Premature.
  Revisit only if read latency ever becomes a problem.

## Section 1 — Selection & excerpt logic

New service `app/services/proof_card_service.py`, layered on `snippet_service`. Input: the
latest scan's client-owned results (`competitor_id IS NULL`) + the client's competitor
names. Output: ordered list of `{kind, platform_label, category, excerpt}`.

**Win extraction** — reuses `snippet_service.build_excerpt(response_text, brand, competitors)`
unchanged. Qualifies when `brand_detected` is true and an excerpt returns. "Best" ranking:
`recommendation`/`local` category first, then low `recommendation_position` (#1–3), then `brand`.

**Loss extraction** — new `build_loss_excerpt(response_text, brand, competitors)`:
- Fires only when the brand is **absent** from the text.
- Returns the first sentence containing **any** competitor name, with that name redacted to
  `[a competitor]` (reusing `snippet_service._redact` + the word-boundary matcher). Never
  names or promotes a rival.
- Restricted to `recommendation`/`local` categories. No competitor in the text → no card
  (we never manufacture a loss).

**Selection cap:** at most **2 wins + 1 loss** for the overview hero; full per-result set
for the scan page. Computed on read — no persistence, no migration. Zero qualifying answers
→ render nothing.

**Guardrail:** the service returns only the finished excerpt string; `response_text` never
enters a return value.

## Section 2 — API shape & schema

New whitelisted schema in `app/schemas/client_view.py`:

```python
class ClientViewProofCard(BaseModel):
    kind: str            # "win" | "loss"
    platform_label: str  # "ChatGPT" | "Perplexity" | "Gemini" | "Claude"
    category: str        # recommendation | local | brand | comparison
    excerpt: str         # redacted, sentence-level — never raw response_text
```

Attachments:
- `ClientViewOverview` gains `proof_cards: list[ClientViewProofCard] = []` (capped 2 wins +
  1 loss). Gated to non-prospects, consistent with `change_narrative`/`benchmark`.
- `ClientViewScanResult` gains `excerpt: str | None = None` and `excerpt_kind: str | None = None`
  (`None` when the result has no qualifying excerpt).

Backend wiring: the existing view service that builds the overview and scan payloads calls
`proof_card_service`, passing latest-scan client-owned results + competitor names (same pattern
as the admin snippet endpoint, `scans.py:159`). **No new endpoint** — data rides on the
overview and scan responses already fetched. No extra client round-trips.

**Prospect gating (scan page):** `excerpt` and `excerpt_kind` on `ClientViewScanResult` are
populated for converted clients only. Prospects receive the same question list with seen/not-seen
badges but both fields are `None` — consistent with the overview proof-card gating
(`proof_cards: []` for prospects). This ensures verbatim AI excerpts are never surfaced during
the pitch stage.

Frontend types mirrored in `src/types/index.ts`.

## Section 3 — UI rendering

**Overview hero** (`frontend/src/app/view/[token]/page.tsx`): new `ProofCardList` component,
placed after the "What Changed" narrative and before the pipeline value card. Narrative flow:
where you stand → what changed → here's the literal proof → what it's worth. Per card:
- Platform chip + kind label.
- **Win:** green (`score-strong`) accent; header "What ChatGPT said about you"; quoted excerpt.
- **Loss:** amber (`score-watch`) accent; header "ChatGPT recommended a competitor — they're
  winning this question"; quoted excerpt. Opportunity framing, matching "What We're Working On".
- Empty `proof_cards` → renders nothing.

**Scan page** (`frontend/src/app/view/[token]/scan/page.tsx`): when a row has an `excerpt`,
add a lightweight expandable "See what AI said" disclosure under the row rendering the same
quoted excerpt. Update the file header comment: curated, redacted excerpts now appear; raw
responses still never do.

**Styling:** reuses existing `rounded-lg border bg-card` + `score-strong`/`score-watch` tokens.
No new design system. Live HTML text — accessible, selectable, responsive, SEO-safe.

**Language compliance (CLAUDE.md §2):** approved vocabulary only — "Seen by AI", "recommended a
competitor", "you weren't mentioned". Never "cited/mentioned/citation".

## Testing

- `proof_card_service`: win extraction delegates correctly; `build_loss_excerpt` returns the
  redacted competitor sentence only when brand absent and competitor present; category
  restriction honored; cap of 2 wins + 1 loss; empty input → empty output; `response_text`
  never present in any returned object.
- Client-view API: overview includes `proof_cards` for clients, omitted/empty for prospects;
  scan results carry `excerpt`/`excerpt_kind`; no `response_text` field on any client-view
  payload (extend existing whitelist assertions).
- Frontend: cards render for win and loss; nothing renders when empty; scan disclosure toggles.

## Out of scope (this iteration)

- Hallucination cards (flagged false statements). Natural next increment.
- Persisting/precomputing cards (Approach C).
- Client-facing PNG download (admin PNG export already exists and is untouched).
