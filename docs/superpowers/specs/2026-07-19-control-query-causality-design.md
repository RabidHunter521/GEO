# Control-Query Causal Proof (Spec 1) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

Every premium client eventually asks the skeptic's question: *"Would my AI
visibility have improved anyway, without you?"* Today every chart we show is
correlational — score went up while we worked. The answer that ends the
conversation is a control group: a set of queries we deliberately do NOT optimize,
tracked on every scan. When the optimized set climbs and the control set doesn't,
the causal story is on one chart. No competitor tool shows this.

## Decisions

- **Controls are admin-defined per client** (not auto-generated). Faris picks
  adjacent-but-untargeted queries — e.g. a service line or neighboring city the
  retainer isn't working on. Auto-generation risks picking queries that content
  work accidentally touches, poisoning the control.
- **Controls never influence anything downstream.** Excluded from the GEO score,
  win/loss, content roadmap, action center, gap matrix, alerts. They are
  measurement-only. This is the invariant the whole feature rests on.
- **Cap: 5 control queries per client** (`MAX_CONTROL_QUERIES` in constants).
  Cost: +5 queries × enabled platforms per scan (~+25% on a full scan) — accepted.
- **Client-facing language:** "Queries we optimized vs. queries we left alone."
  Never "control group" jargon on client surfaces; never banned vocabulary
  (visibility frequency, Seen by AI).

## Design

### 1. Data model (one migration)

New model `backend/app/models/control_query.py`:

```
ControlQuery: id, client_id (FK CASCADE), query_text, category,
              active (bool, default True), created_at
```

`ScanQueryResult` gains `is_control: Mapped[bool]` (server_default false). Existing
rows unaffected. RLS enabled on the new table per seenby-migrations runbook.

### 2. Scan engine

`query_builder` gains a step: after building the standard ≤20/platform set, append
the client's active `ControlQuery` rows (marked so the runner sets
`is_control=True` on their result rows). Control queries run on every enabled
platform like any other query — same retry/flag semantics. They do NOT count
against the 20-query category structure (they're additive, capped at 5).

### 3. Downstream exclusion (the invariant)

Every consumer that aggregates `ScanQueryResult` must filter
`is_control == False`: `scoring_service`, `win_loss_service`,
`gap_matrix_service`, `competitor_intelligence_service`, action center,
content-gap/roadmap inputs, alert thresholds, proof-card selection. Implementation
note for the plan: add the filter at each service's base query; add a regression
test per service asserting a control row never changes its output.

### 4. The causal chart

New service function (e.g. `causality_service.compute_causal_trend(client_id)`):
per completed scan, two series — visibility frequency of the optimized set
(existing client-owned, non-control rows) and of the control set — over time.
Compute-on-read from stored results (booleans survive the 90-day raw-response
purge, so history is durable).

Surfaces:
- **Admin** — a "Proof of impact" panel on `/clients/[id]/scan` (two-line trend).
- **Monthly PDF** — a "Did our work cause this?" section: the two-line chart +
  one deterministic sentence, e.g. *"Queries we worked on: seen by AI 64% of the
  time, up from 38%. Queries we left alone: 31%, up from 29%."* No LLM.
- **Client view overview** — same chart, shown only when ≥2 scans of control
  history exist (a single point proves nothing).

### 5. Admin UI

Manage controls on `/clients/[id]/settings` (add/deactivate; deactivate, never
delete — history must survive). Guardrail copy in the UI: "Pick queries the
retainer will NOT touch. If we later work on one, deactivate it."

## Scope boundaries

**In scope:** model + migration, query_builder addition, exclusion filters +
regression tests, causal trend service, three surfaces, settings UI.
**Out of scope:** auto-selection of controls; statistical significance testing
(two honest lines beat a p-value here); any score formula change (none — no
SCORE_VERSION bump); scheduled scans.

## Risks

- **Contaminated controls** (work accidentally improves a control query) make the
  chart look like "we did nothing." Mitigation: deactivation flow + the settings
  guardrail; deactivated controls drop out of the series from that date.
- **Small-N noise:** 5 queries × 4 platforms = 20 samples/scan; the line will
  wobble. Mitigation: render as a smoothed/aggregate trend across scans, and the
  ≥2-scan display gate.
- Cost creep on scan runs — bounded by the cap and per-client platform toggles.

## Testing

- Builder: controls appended, capped, `is_control` set; inactive controls skipped.
- Exclusion: for each downstream service, output identical with and without a
  control row present (the invariant tests).
- Trend: correct split of series; deactivated controls excluded after
  deactivation; display gate honored on client view.
- Language sanitizer green on all client-facing strings.

## Success criteria

A client with 3+ months of history sees one chart: the queries SeenBy worked on
climbing, the untouched benchmark flat — on the portal and in the PDF — with
zero effect of control rows on score, roadmap, or alerts.
