# Retention Narrative Fixes (Spec 0) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

Verified 2026-07-19: the product already computes client-specific "here's why"
evidence, but two surfaces ship boilerplate instead of using it — at exactly the
moments a client decides whether the retainer is worth it.

1. **Flat-score weekly digest.** `claude_action.py:17-27` gates the Claude-generated
   action on a ±5pt score move. Below that, the digest tip falls to
   `DIGEST_STATIC_TIPS[band]` (`core/constants.py:120-126`) — five hardcoded strings
   keyed only by score band, identical for every client in the band, zero reference
   to that client's queries, competitors, or state. A flat score is the nervous-client
   moment; the most frequent touchpoint answers it with generic filler.
2. **Headline battle silently dropped from the client portal.**
   `api/v1/client_view.py` (~436-476) computes and returns `headline_battle` on
   `GET /view/{token}/competitors`, but
   `frontend/src/app/view/[token]/competitors/page.tsx` never renders it. The
   client sees "Your competitors are winning here" with no "the one move to flip
   it" — even though the move is already in the API payload.

## Decisions

- **No new LLM calls.** The ±5pt Claude gate stays (cost control). The flat-score
  fix is a deterministic personalization ladder over data already loaded, in the
  spirit of `headline_battle_service` (deterministic, zero-LLM).
- **No new data, no migration.** Both fixes consume existing computed state.

## Design

### Fix A — deterministic personalized tip for the flat-score digest

New function in `digest_service.py` (or a small `digest_tip_service.py`):
`select_digest_tip(client, digest_data) -> str`, replacing the direct
`DIGEST_STATIC_TIPS` lookup in the sub-±5pt path. Priority ladder — first match wins:

1. **Battle-derived tip** — if `digest_data` already carries a headline battle
   (it's computed at `digest_service.py:~200` regardless of score movement):
   *"Your score held steady this week. The fastest path to moving it: '{query}' —
   {rival} is currently the one seen by AI there."* (Names real query + rival;
   complements rather than duplicates the battle block, which pitches the move.)
2. **Toolkit-derived tip** — if `technical_foundations_verified` or
   `structured_data_verified` is False on the client: name the specific unverified
   file(s): *"Your llms.txt isn't verified live yet — publishing it is the quickest
   score gain available this week."*
3. **Weakest-dimension tip** — deterministic template per dimension, filled with
   the client's actual weakest dimension name and score.
4. **Band tip fallback** — existing `DIGEST_STATIC_TIPS[band]`, kept as the floor
   (e.g., brand-new client with no scan data).

All strings pass `language_sanitizer`; every interpolated value HTML-escaped.
Rungs 1–3 must only fire when the underlying data genuinely exists — no invented
specifics (prompt-audit rule: no claim without stored evidence).

### Fix B — render `headline_battle` on `/view/[token]/competitors`

Frontend-only. In `competitors/page.tsx`, render a battle card when
`data.headline_battle` is present, above or beside the existing "Your competitors
are winning here" callout: rival name, the query (verbatim), platform label, and
the move (`move_title` + `move_angle`) when present. When `move_title` is null,
use the existing degrade copy ("The play to flip it is being prepared") —
consistent with digest/PDF wording (`digest_service.py:~324`). Styling: existing
shadcn card patterns already on that page; 3-band traffic-light rules unaffected.
Null-safe: absent field renders nothing (older cached payloads).

## Scope boundaries

**In scope:** the tip ladder + its wiring in the flat-score digest path; the
battle card on the client-view competitors page.
**Out of scope:** any change to the ±5pt Claude gate or the Claude action prompt;
PDF changes (already grounded); new API fields; redaction changes
(`/view/competitors` already names rivals — established in the war-narrative spec).

## Testing

- Tip ladder: each rung fires only when its data exists; ladder order respected;
  band fallback when nothing else applies; no banned vocabulary; HTML-escaped.
- Digest snapshot: flat-score digest with a battle present shows the battle-derived
  tip, not the band tip.
- Client view: battle card renders with full battle; degrade copy when no move;
  nothing rendered when `headline_battle` absent; no `response_text` leakage
  (payload unchanged — assert schema untouched).

## Success criteria

A flat-score client's weekly digest names something specific to *them* every week,
and the client portal's competitors page shows the same "one move to flip it" the
email and PDF already show. Zero new LLM calls, zero migrations.
