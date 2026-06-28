# Evidence View Surfacing — Design Spec

**Date:** 2026-06-28
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Faris + Claude

## Problem

SeenBy's "receipts" engine — verbatim AI-answer proof cards — is already built
(`snippet_service`, `proof_card_service`) but is **not distributed to the buyer**.
Today the receipts reach the client only as a single redacted quote in the weekly
email digest. The two flagship client-facing deliverables — the public client view
(`/view/[token]`) and the monthly PDF — show **no receipts at all**. The strongest
emotional lever (naming the rival who won) is redacted away on every surface.

This rung makes the existing evidence engine visible where the buyer actually looks,
and introduces a surface-aware naming rule so rivalry drives renewal without giving
competitors free exposure on publicly shareable artifacts.

This is rung 1 of a 5-rung value ladder (evidence → money → war narrative →
done-for-you fix → reputation loop). Only rung 1 is in scope here.

## Current State (verified)

- `app/services/snippet_service.py` — `build_excerpt` (win), `build_loss_excerpt`
  (loss), `render_snippet_png`. Competitor names are **hardcoded-redacted** to
  `[a competitor]`.
- `app/services/proof_card_service.py` — `select_proof_cards` returns best 2 wins +
  1 loss as `ProofCard(kind, platform, category, excerpt)`. Carries **only the
  redacted excerpt**, never `response_text` — safe for public surfaces by contract.
- `app/services/digest_service.py` — calls `select_proof_cards`, surfaces only
  `cards[0].excerpt` as a single quote block.
- `app/api/v1/scans.py` — `GET /scans/{id}/results/{id}/snippet.png`, admin-key
  gated, **win-only**. Unchanged by this work.
- `app/api/v1/client_view.py` — public token-gated client view. **No proof cards.**
- `app/services/report_service.py` — monthly PDF. **No proof cards.**

## Design

### 1. Redaction becomes a parameter (the naming spine)

Redaction shifts from a hardcoded constant to an explicit caller choice:

- `snippet_service.build_loss_excerpt(response_text, brand, competitors, redact: bool = True)`
  — default `True` (safe). When `False`, the competitor sentence is returned with
  the rival named instead of `[a competitor]`.
- `proof_card_service.select_proof_cards(..., redact_competitors: bool = True)`
  — passes the flag through to excerpt building.

**Surface classification:**

| Surface | Audience | `redact` | Loss card reads |
|---|---|---|---|
| Weekly email digest | Owner's inbox (private) | `False` | "Your competitor Dr. Lim Dental is winning here" |
| Monthly PDF report | Owner, you review (private) | `False` | named |
| Public client view `/view/[token]` | Link-shareable (public) | `True` | "[a competitor]" |
| Admin scan PNG endpoint | Admin only | `True` (unchanged) | "[a competitor]" |

Rationale: `/view/[token]` is forwardable, so it is treated as **public/redacted**
even though it is gated by a share token. Only inbox-delivered artifacts name rivals.

### 2. Win + Loss pairing as the core unit

The surfaced unit is a **pair** (a win card beside a loss card), because the
contrast carries the emotional payload. Each surface degrades gracefully:

- Win + loss both present → show the pair.
- Only one present → show the single card.
- Neither present → show nothing (no empty scaffolding). Zero loss cards is a
  *good-news* state (client wins everywhere / no competitor named) and any
  surrounding copy must frame it positively, not as missing data.

**Per-surface treatment:**

- **Digest:** upgrade the existing single-quote `proof_block` to a win+loss pair
  ("✅ What ChatGPT said about you" / "⚠️ Who it recommended instead — *Dr. Lim
  won this one*"). Loss named (`redact=False`).
- **Public client view (`/view/[token]`) — net-new:** a "Straight from AI" strip on
  the overview rendering the same 2 wins + 1 loss as on-page cards via
  `select_proof_cards(..., redact_competitors=True)`.
- **Monthly PDF — net-new:** a "What AI said about you this month" section with
  win/loss proof cards (rival named, `redact=False`), placed next to the existing
  "what changed this month" narrative.

### 3. Language compliance

All client-facing copy uses approved language (CLAUDE.md §2): "Seen by AI" /
"Not seen by AI", and "your competitor X is winning here" for the loss framing.
Never surface confidence scores, char offsets, token counts, or raw API responses.
The `ProofCard` contract already guarantees no `response_text` leaks.

## Scope Boundaries

**In scope:** redaction-as-parameter; win+loss pairing in digest (upgrade),
`/view` overview (net-new), monthly PDF (net-new); graceful one-card / zero-card
degradation; approved language.

**Explicitly out of scope (later rungs / separate specs):**

- Money / "patients at risk" RM estimator (rung 2).
- Competitor war *narrative* prose / "one move to flip it" (rung 3).
- Done-for-you toolkit implementation (rung 4); reputation loop (rung 5).
- Any new scan-engine data, new platforms, or schema migrations — reads existing
  `scan_query_results`.
- Changes to the admin PNG endpoint or score formula.

## Testing

- `snippet_service`: `build_loss_excerpt` with `redact=False` names the rival;
  with `redact=True` (default) still produces `[a competitor]`. Existing redaction
  tests must continue to pass.
- `proof_card_service`: `redact_competitors=False` propagates to loss excerpts;
  default behavior unchanged; win/loss caps and ordering unchanged.
- `digest_service`: win+loss pair rendered when both exist; single-card and
  zero-card fallbacks; loss card names rival; HTML-escaped.
- `client_view`: proof-card strip present, redacted, no `response_text` in payload;
  zero-card state renders nothing (no empty scaffold).
- `report_service`: PDF section present with named loss card; absent when no cards.
- Regression: no client-facing surface exposes raw `response_text` or banned terms.

## Success Criteria

- The win+loss proof pair appears in the digest, the `/view` overview, and the
  monthly PDF.
- Rival named in digest + PDF; redacted in `/view` and admin PNG.
- Zero-card and one-card states degrade cleanly and read as good news where
  applicable.
- No raw responses or banned language on any client surface; existing tests green.
