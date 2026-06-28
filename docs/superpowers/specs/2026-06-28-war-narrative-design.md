# War Narrative (Rung 3 — Headline Battle) — Design Spec

**Date:** 2026-06-28
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Faris + Claude

## Problem

Rungs 1–2 gave the clinic owner the receipts (the verbatim AI answer) and the money
(captured + at-risk). The persona's renewal hook is sharper and more focused than
either: *"Dr. Lim is winning invisalign KL — here's the one move to flip it."* One
named rival, one specific lost battle, one move — surfaced as rivalry prose in the
renewal-driving comms, not another planning table.

The codebase already has the raw material: `win_loss_service` classifies each query
`won/lost/shared/open` with the competitors seen; `content_brief_service` produces a
Claude-written brief (title/angle/outline) for a lost query; `content_roadmap` is the
multi-item 90-day plan; `competitor_intelligence_service` flags `is_winning`. Rung 3
is **not** new data or another plan — it is a deterministic *focusing narrative* layer
that picks the single most important lost battle, names the rival, and states the one
move, reusing the brief that already exists.

This is rung 3 of the 5-rung evidence value ladder (rung 1:
`2026-06-28-evidence-view-surfacing-design.md`; rung 2:
`2026-06-28-value-at-risk-design.md`). Only rung 3 is in scope.

## Decisions (from brainstorming)

- **Core unit:** a single headline battle (one rival × one lost query × one move),
  not a top-3 list and not a per-rival narrative.
- **Engine:** deterministic server-side selection (no LLM); the "one move" reuses the
  existing `ContentBrief`.
- **Degrade:** no Claude call ever fires in an automated flow. If the picked battle
  has no brief, the battle is still named and the move text degrades.

## Current State (verified)

- `app/services/win_loss_service.py` — `compute_win_loss(client_id, db)` reads the
  latest completed scan's client-owned, non-hallucination results in
  `WIN_LOSS_CATEGORIES`, runs `detect_brand_mention` per competitor, and
  `classify_result(client_seen, competitors_seen)` → `won/lost/shared/open`. Already
  joins `ContentBrief` by `scan_query_result_id`. Admin-only (uses `response_text`).
- `app/services/content_brief_service.py` — `generate_brief_for_result(...)` (admin,
  on-demand, Claude). Rung 3 does **not** call this.
- `app/services/proof_card_service.py` — category-priority ordering
  (`recommendation` 0, `local` 1, `brand` 2, `comparison` 3) — reused for ranking.
- `app/models/content_brief.py` — `ContentBrief(scan_query_result_id, title, angle,
  outline, competitors_seen, ...)`.
- `app/api/v1/client_view.py` — `/view/{token}/competitors` (non-prospect gated)
  already returns competitor names, `is_winning`, and per-competitor `takeaway`.

## Design

### 1. Selection engine (deterministic, no LLM)

New unit `app/services/headline_battle_service.py`:

```
select_headline_battle(client_id, db) -> HeadlineBattle | None
```

`HeadlineBattle` dataclass: `rival_name: str, query_text: str, platform_label: str,
category: str, move_title: str | None, move_angle: str | None`.

Algorithm:
1. Reuse the latest-scan win/loss classification (call `compute_win_loss` or the same
   query path) to get entries; keep only `outcome == "lost"` (client not seen AND
   ≥1 competitor seen).
2. If no lost entries → return `None`.
3. **Primary threat** = the competitor appearing in the most lost battles (tie broken
   by name for determinism). This is the rival the headline names.
4. **Pick the battle**, ranked by: category priority (`recommendation` → `local`
   first, via the proof-card ordering), then prefer a battle whose `competitors_seen`
   includes the primary threat, then ascending `recommendation_position` (None last),
   then `created_at`.
5. `rival_name` = the primary threat if present in the picked battle, else the first
   `competitors_seen`. `platform_label` via `PLATFORM_LABELS`.
6. `move_title` / `move_angle` = the existing `ContentBrief` for that result if one
   exists, else `None`. **No brief is generated here** — no Claude call.

Pure compute-on-read: no persistence; no `response_text` on the returned struct.

### 2. Surfaces

All name the rival (private surfaces + the client-view page that already names rivals).

| Surface | Change |
|---|---|
| Weekly digest | Net-new "battle" block. With move: *"Your competitor {rival} is winning '{query}' on {platform}. The one move to flip it: {move_title} — {move_angle}."* Without move: *"…the play to flip it is being prepared."* |
| Monthly PDF | Net-new "The battle to win next" section, same content, styled like the existing stat/proof blocks |
| Client view `/view/competitors` | Add a nested `headline_battle` field to the competitors response, serialized from the struct (rival, query, platform, move_title, move_angle) |

`/view/competitors` is non-prospect gated and already names rivals openly, so naming
there needs **no redaction logic** (consistent with rung 1's split-by-surface rule).
The forwardable overview is deliberately left out. The "one move" (brief title/angle)
is client-safe content — same class as the content-gaps/roadmap suggestions already on
the client view. Every interpolated value in email/PDF HTML is `html.escape`-d.

### 3. Data flow

- Digest (`_compute_digest_data`) and PDF (`_gather_report_data`): call
  `select_headline_battle(client.id, db)`; pass the struct (or its fields) into the
  HTML builder; render the block only when the struct is not `None`.
- Client view competitors endpoint: call `select_headline_battle`, map to a
  whitelisted `ClientViewHeadlineBattle` schema, attach to `ClientViewCompetitors`.

## Scope Boundaries

**In scope:** `headline_battle_service` + `HeadlineBattle`; deterministic selection
reusing win/loss + brief lookup + category ordering; three surfaces (digest, PDF,
`/view/competitors`); approved language; graceful degradation; `None` when no battle.

**Out of scope:**
- No new LLM calls in any automated flow — rung 3 only reads briefs; brief generation
  stays in the existing admin win/loss flow.
- No new scan data, no DB migration. The `/view/competitors` schema gains a nested
  response field only (Pydantic).
- Top-3 lists, per-rival narratives (rejected forks).
- Overview placement / any new redaction logic.
- Rungs 4–5.

## Risks

- Selection rides on `response_text`-derived win/loss from the **latest scan only**
  (90-day retention) — same caveat `win_loss_service` already carries.
- `ContentBrief` is keyed per `scan_query_result_id`, so after a fresh scan briefs
  won't match until regenerated — the "one move" will often be absent right after a
  scan and degrade to the "play being prepared" text. Acceptable (and a nudge for the
  admin to generate briefs); noted so it isn't mistaken for a bug.
- The "primary threat" tie-break is a heuristic; documented so selection is
  predictable.

## Testing

- `headline_battle_service.select_headline_battle`: `None` when no lost battle (all
  won / no competitors); picks the highest-priority-category lost query; names the
  primary threat (the competitor in the most lost battles); reuses an existing brief
  (move_title/angle populated) and degrades to `None` move when no brief; never calls
  Claude (no `content_brief_service` import in the automated path); struct carries no
  `response_text`.
- `digest_service`: battle block rendered when a battle exists; "play being prepared"
  fallback when no brief; absent when no battle; HTML-escaped; rival named.
- `report_service`: "battle to win next" section present/absent symmetrically; rival
  named; approved language.
- `client_view` competitors: `headline_battle` present when a battle exists, absent
  (None) otherwise; no `response_text` or internal fields in the payload; prospects
  still get the uniform 404 on the competitors surface (unchanged).
- Regression: no banned vocabulary on touched surfaces; no automated-flow Claude call.

## Success Criteria

- The single headline battle — named rival, lost query, one move — appears on the
  weekly digest, the monthly PDF, and `/view/competitors`.
- Selection is deterministic and fires zero LLM calls in automated flows.
- Every surface degrades cleanly: no battle → absent; battle without a brief → battle
  shown, move degrades.
- No `response_text` or banned language on any surface; existing tests stay green.
