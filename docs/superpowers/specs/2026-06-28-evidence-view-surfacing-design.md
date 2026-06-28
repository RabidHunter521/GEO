# Evidence View Surfacing — Design Spec

**Date:** 2026-06-28
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Faris + Claude

## Problem

SeenBy's "receipts" engine — verbatim AI-answer proof cards — is already built
(`snippet_service`, `proof_card_service`). It reaches two surfaces today: a single
**win-only** quote in the weekly email digest, and a redacted 2-win + 1-loss set on
the public client view (`/view/[token]/overview`). Two gaps remain: the **monthly
PDF** — the flagship reviewed deliverable — shows **no receipts at all**, and the
strongest emotional lever (naming the rival who won) is **redacted on every surface**,
including the private inbox-delivered ones where rivalry legitimately drives renewal.

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
- `app/services/digest_service.py` — calls `select_proof_cards` with
  `win_cap=1, loss_cap=0`, surfaces only `cards[0].excerpt` as a single **win-only**
  quote block. **No loss card; rival never named.**
- `app/api/v1/client_view.py:258-292` — public client view `/overview` **already
  surfaces** 2 wins + 1 loss via `select_proof_cards` (redacted), serialized through
  `ClientViewProofCard`. `/scan` shows per-result excerpts via `result_excerpt`.
  **Stays as-is** (public ⇒ redacted). No change in this work.
- `app/api/v1/scans.py` — `GET /scans/{id}/results/{id}/snippet.png`, admin-key
  gated, **win-only**. Unchanged by this work.
- `app/services/report_service.py` — monthly PDF. **No proof cards.** Net-new.

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

- **Digest (upgrade):** raise the caps to `win_cap=2, loss_cap=1` and pass
  `redact_competitors=False`; upgrade the single-quote `proof_block` to a win+loss
  pair ("✅ What ChatGPT said about you" / "⚠️ Who it recommended instead — *Dr. Lim
  won this one*"). Loss named.
- **Public client view (`/view/[token]`) — no change:** already surfaces 2 wins +
  1 loss redacted (`client_view.py:258-292`). Stays redacted because the token URL
  is forwardable (public). Explicitly left untouched.
- **Monthly PDF — net-new:** a "What AI said about you this month" section with
  win/loss proof cards (rival named, `redact_competitors=False`), placed next to the
  existing "what changed this month" narrative. Adds a `proof_cards` field to
  `ReportData`, populated in `_gather_report_data` from the already-loaded
  `client_results`, and rendered in `_build_report_html`.

### 3. Language compliance

All client-facing copy uses approved language (CLAUDE.md §2): "Seen by AI" /
"Not seen by AI", and "your competitor X is winning here" for the loss framing.
Never surface confidence scores, char offsets, token counts, or raw API responses.
The `ProofCard` contract already guarantees no `response_text` leaks.

## Scope Boundaries

**In scope:** redaction-as-parameter (`snippet_service` + `proof_card_service`);
digest upgrade (win+loss pair, rival named); monthly PDF proof section (net-new,
rival named); graceful one-card / zero-card degradation; approved language.

**Already done / deliberately untouched:** the public client view overview already
renders 2 wins + 1 loss redacted — left as-is (public ⇒ redacted). The admin PNG
endpoint is unchanged.

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
- `client_view` (regression only): overview proof cards remain **redacted**
  (default `redact_competitors=True` unchanged); existing tests stay green.
- `report_service`: PDF section present with named loss card; absent when no cards.
- Regression: no client-facing surface exposes raw `response_text` or banned terms;
  the public/admin defaults stay redacted.

## Success Criteria

- The win+loss proof pair appears in the digest, the `/view` overview, and the
  monthly PDF.
- Rival named in digest + PDF; redacted in `/view` and admin PNG.
- Zero-card and one-card states degrade cleanly and read as good news where
  applicable.
- No raw responses or banned language on any client surface; existing tests green.
