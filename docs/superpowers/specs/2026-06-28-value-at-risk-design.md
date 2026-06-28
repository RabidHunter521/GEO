# Value at Risk (Rung 2 — Money Estimator) — Design Spec

**Date:** 2026-06-28
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Faris + Claude

## Problem

SeenBy proves AI *visibility* but not *money*. The clinic-owner persona's sharpest
objection is "did this put a butt in a chair?" — a visibility score does not justify
a retainer; an estimated ringgit figure does. Rung 1 surfaced the verbatim AI
"receipts"; rung 2 attaches a money number to them.

The existing `revenue_service.estimate_pipeline` already answers *"what did AI
visibility GET me?"* — it runs realized AI-referral visitors through a
visitor→lead→deal→close chain and returns `None` until the admin configures
`avg_deal_value_rm`. Rung 2 adds the inverse — *"what is AI invisibility COSTING
me?"* — and presents the two as a pair: captured value (ROI proof) beside value at
risk (urgency to keep paying).

This is rung 2 of the 5-rung evidence value ladder (see
`2026-06-28-evidence-view-surfacing-design.md` for rung 1). Only rung 2 is in scope.

## Decisions (from brainstorming)

- **Story:** paired — "we captured ≈RM Y; ≈RM X is still on the table."
- **At-risk model:** gap-scaled bootstrap off the existing realized chain (not a
  per-query demand model, not a flat per-query value).

## Current State (verified)

- `app/services/revenue_service.py` — `estimate_pipeline(ai_visitors, client) ->
  PipelineEstimate | None`. Chain: `leads = visitors × visitor_to_lead_pct`;
  `pipeline_rm = leads × avg_deal_value_rm`; `won_rm = pipeline_rm ×
  lead_to_customer_pct`. Returns `None` unless `avg_deal_value_rm` is set; conversion
  percentages fall back to `DEFAULT_VISITOR_TO_LEAD_PCT` /
  `DEFAULT_LEAD_TO_CUSTOMER_PCT`.
- `Client` model already carries `avg_deal_value_rm`, `visitor_to_lead_pct`,
  `lead_to_customer_pct` — no new admin inputs, no migration.
- `app/api/v1/client_view.py` overview already builds `ClientViewTrafficValue` from
  the latest traffic snapshot's visitors via `estimate_pipeline`, and has
  `latest.ai_citability` in hand.
- `app/services/report_service.py` — `ReportData.pipeline: PipelineEstimate | None`
  populated in `_gather_report_data` (has `current_gs.ai_citability` and
  `ai_visitors_current`).
- `app/services/digest_service.py` — `_compute_digest_data` has `current_citability`
  but loads **no** traffic snapshot / visitor count and surfaces **no** money.

## Design

### 1. The model (`revenue_service`)

New unit beside `estimate_pipeline`, reusing the identical conversion chain so the
two numbers are directly comparable (same deal value, same percentages):

```
f = visibility_frequency (fraction in [0, 1])       # latest scan AI visibility
V = ai_visitors (realized AI-referral visitors)      # latest traffic snapshot
gap_multiplier = min( (1 - f) / max(f, MIN_VIS), MAX_MULT )
missed_visitors = V × gap_multiplier
missed_leads     = missed_visitors × visitor_to_lead_pct / 100
missed_pipeline  = missed_leads × avg_deal_value_rm
missed_won       = missed_pipeline × lead_to_customer_pct / 100
```

Signature:
`estimate_value_at_risk(ai_visitors: int | None, visibility_frequency: float | None,
client: Client) -> ValueAtRisk | None`

`ValueAtRisk` dataclass mirrors `PipelineEstimate`:
`ai_visitors, missed_visitors, missed_leads, missed_pipeline_rm, missed_won_rm,
avg_deal_value_rm, visitor_to_lead_pct, lead_to_customer_pct, gap_multiplier`.

**Guardrails (conservative — never overstate the loss):**
- `MIN_VIS = 0.25` — floor `f` at 25% so a tiny visibility score can't explode the
  gap (raw multiplier at f=0.10 is 9×; floored it is ≤3×).
- `MAX_MULT = 3.0` — hard cap: at-risk is never more than 3× captured.

Both are named constants in `app/core/constants.py` (no magic numbers, CLAUDE.md §3).

**Gating (identical discipline to `estimate_pipeline`):** returns `None` unless
`avg_deal_value_rm > 0` AND `ai_visitors` is not None AND `visibility_frequency` is
not None. Conversion percentages fall back to the same `DEFAULT_*` constants.

**Emergent properties:** at f=1.0 → missed=0 ("you're capturing it all"); at f=0 →
floored to MIN_VIS, capped at MAX_MULT (no divide-by-zero); V=0/None → `None`.

### 2. Surfaces

| Surface | Today | Change |
|---|---|---|
| Client view overview | `traffic_value` = captured only | Extend `ClientViewTrafficValue` schema with at-risk fields; populate via `estimate_value_at_risk(latest_traffic.ai_visitors, latest.ai_citability/100, client)` |
| Monthly PDF | `ReportData.pipeline` (captured) | Add `ReportData.value_at_risk: ValueAtRisk | None`, populate in `_gather_report_data` from `ai_visitors_current` + `current_gs.ai_citability/100`, render beside the captured pipeline section |
| Weekly digest | no money | Net-new: load the latest `AiTrafficSnapshot` for the client, compute the pair, add a paired money block to `DigestData` + the email HTML |

`f` is `ai_citability` expressed as a fraction (`/100`). Each surface uses the latest
score and latest traffic snapshot it already has (or, for the digest, newly loads).

**Copy:** "AI visibility got you ≈RM Y this month · ≈RM X (≈N potential customers)
still on the table." Whole money block hidden when either estimate is `None`. All
figures labeled estimates ("based on") — never presented as measured. Generic
"potential customers" label (no industry-aware variants). Approved language only
(CLAUDE.md §2); no confidence scores / char offsets / token counts surfaced.

### 3. Data flow

- Overview & PDF: read existing latest-score `ai_citability` + latest visitor count;
  call both estimators; serialize the pair.
- Digest: new step loads the latest `AiTrafficSnapshot` (period-descending, first) to
  get `ai_visitors`; uses `current_citability` already computed; calls both
  estimators.
- No competitor naming → no public/private redaction split; the pair may appear on
  the (public) client view exactly as captured already does.

## Scope Boundaries

**In scope:** `estimate_value_at_risk` + `ValueAtRisk` + `MIN_VIS`/`MAX_MULT`
constants; paired captured+at-risk on overview, PDF, and digest; gating identical to
`estimate_pipeline`.

**Out of scope:**
- New config UI / new admin inputs — reuses existing `Client` fields. **No DB
  migration** (schema changes are Pydantic response-only).
- Per-query demand model; external search-volume data.
- Industry-aware "patients vs customers" labeling — one generic label.
- War narrative (rung 3); at-risk feeds it later but no prose is generated here.
- No changes to the scan engine, score formula, or `estimate_pipeline` itself.

## Risks

- The "traffic ∝ visibility" assumption is an assumption; the two guardrails keep the
  number conservative and every figure is labeled an estimate. Acceptable for a
  directional retainer-justification number.
- `f` (latest scan) and `V` (latest traffic snapshot) come from different sources and
  possibly different time windows; we use the latest of each. Acceptable for a
  directional estimate; noted so it is not mistaken for a measured figure.

## Testing

- `revenue_service.estimate_value_at_risk`: returns `None` when `avg_deal_value_rm`
  unset / `ai_visitors` None / `visibility_frequency` None; gap-multiplier math at
  representative f (0.4 → 1.5×, 0.9 → ~0.11×, 1.0 → 0×); `MIN_VIS` floor (f=0.10
  capped to ≤3×); `MAX_MULT` cap (f=0 → 3×, no divide-by-zero); conversion-percent
  fallbacks; figures consistent with `estimate_pipeline` for the same inputs.
- `client_view` overview: at-risk fields present and correct; whole block `None`/absent
  when unconfigured; existing captured behavior unchanged; no raw/internal fields.
- `report_service`: paired section rendered when configured, absent when not; approved
  language; existing pipeline rendering unaffected.
- `digest_service`: latest traffic snapshot loaded; paired money block rendered when
  configured, absent otherwise; HTML-escaped; existing digest content unaffected.
- Regression: no banned vocabulary on touched surfaces; no money number shown without
  `avg_deal_value_rm`.

## Success Criteria

- Captured and at-risk appear together on overview, PDF, and digest, directly
  comparable (same chain).
- The pair is hidden whenever `avg_deal_value_rm` is unconfigured or inputs are
  missing — never a half-number, never a fabricated figure.
- At-risk is conservative (≤3× captured) and never divides by zero.
- Existing `estimate_pipeline` behavior and all current tests remain green.
