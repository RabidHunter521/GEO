# Guarantee Engine (Spec 2) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

Premium agency pricing is bought on risk reversal: *"If your visibility frequency
doesn't improve X points in 90 days, the next month is free."* SeenBy owns the
measurement, so it can underwrite that promise — no competitor dares. Today
nothing in the product can represent a commitment: there's no baseline-target-
deadline object, so the promise (if made) lives in a WhatsApp message and is
invisible on every report. The feature is the *tracking and display* of a
commitment; the commercial remedy (free month) stays out-of-band.

## Decisions

- **Metric options:** overall GEO score or AI Citability (the automatic 40%
  dimension). Recommended default: **AI Citability** — it's fully automatic, so
  the guarantee can't be gamed by adjusting an assisted dimension, and it's the
  dimension the retainer work most directly moves. (Overall score allowed for
  clients where the pitch was score-based.)
- **One active guarantee per client.** A second can only be created after the
  current one is resolved. Keeps every surface unambiguous.
- **Status is computed, outcome is admin-confirmed.** The system derives
  `on_track / at_risk / met / deadline_passed` from scan data; only Faris flips
  the terminal outcome (`met` / `missed`) — mirroring the assessment-service
  "system suggests, admin gates" pattern. No automated flow ever tells a client
  "we failed" without Faris seeing it first.
- **Credibility dependency:** launch after Spec 1 (control queries) and honest
  measurement are in place. A guarantee on top of a shaky metric is a time bomb.

## Design

### 1. Data model (one migration)

New model `backend/app/models/guarantee.py`:

```
Guarantee: id, client_id (FK CASCADE), metric ("overall" | "ai_citability"),
           baseline_value (int), target_value (int),
           start_date (date), deadline_date (date),
           status ("active" | "met" | "missed" | "void"),
           resolved_at (datetime|None), admin_note (Text|None), created_at
```

`void` = cancelled by mutual agreement (e.g. client paused the retainer);
`admin_note` records why. RLS per seenby-migrations runbook.

### 2. Service

`guarantee_service.py`:
- `create_guarantee(...)` — baseline auto-filled from the latest completed scan's
  metric value (admin can override); rejects if an `active` guarantee exists.
- `get_guarantee_progress(client_id) -> GuaranteeProgress | None` — compute-on-
  read: current metric value from the latest scan, points gained vs needed, days
  remaining, derived state:
  - `met` (early): current ≥ target → surface as achieved even before deadline.
  - `on_track`: linear-pace heuristic — points gained ≥ (elapsed/total) × points
    needed, with a grace floor so week 1 isn't instantly "at risk".
  - `at_risk`: behind pace.
  - `deadline_passed`: past deadline, target not met, awaiting Faris resolution.
- `resolve_guarantee(id, outcome, note)` — admin-only terminal transition.

### 3. Surfaces

| Surface | Content |
|---|---|
| Admin `/clients/[id]` detail | Progress widget: metric, baseline → current → target, deadline, derived state, resolve action when deadline passed. |
| Admin `/clients/[id]/settings` | Create / void guarantee. |
| Client view overview | "Our commitment" card: *"We committed to lifting your AI visibility from {baseline} to {target} by {date}. Today: {current}."* Progress bar. Shows `on_track`/`met` states plainly; an `at_risk` state renders as neutral progress (bar + numbers, no red alarm) — the numbers speak, Faris does the narrative. Hidden entirely for `void`; `missed` shown only after Faris resolves (with his note's client-safe framing). |
| Monthly PDF | Same commitment block in the header area — the report opens with the promise and where it stands. |
| Weekly digest | One line when a guarantee is active: current vs target + days left. |

Color: reuse the 3-band traffic-light utilities where a color is warranted
(progress toward target), never ad-hoc colors. All copy through
`language_sanitizer`; no banned vocabulary.

### 4. Alerting

When state transitions to `at_risk` or `deadline_passed`, email ALERTS_EMAIL
(+ Telegram best-effort) — Faris finds out before the client does. Evaluated at
scan completion (synchronous, best-effort, same pattern as `alert_service`).

## Scope boundaries

**In scope:** model + migration, service, five surfaces, admin create/resolve
flow, at-risk alerting.
**Out of scope:** billing/refund automation (no billing in MVP); multiple
concurrent guarantees; guarantees on assisted dimensions or traffic; any
automated client-facing "missed" messaging.

## Risks

- **A missed guarantee is a churn event with receipts.** That's the point — it
  forces honest target-setting. Mitigation: baseline auto-fill + Faris sets
  targets manually; the admin widget shows pace from day one.
- Metric volatility (platform outages can dip a scan). Mitigation: progress reads
  the latest *completed* scan; Faris controls when scans run (on-demand) and the
  terminal outcome.
- Legal wording of the promise is a business matter — the product shows numbers
  and dates, the contract defines the remedy. `admin_note` keeps the paper trail.

## Testing

- Service: create rejects duplicate active; baseline auto-fill; each derived
  state reachable (met early, on track, at risk, deadline passed); resolve
  transitions and locks.
- Surfaces: card present only when appropriate per status table; `void` hidden;
  `missed` hidden until resolved; sanitizer green; PDF renders the block.
- Alerting: fires on state transition only (not every scan), best-effort
  swallow on failure (never blocks the scan).

## Success criteria

Faris can put a written commitment on a client's portal and PDF in 2 minutes,
watch pace weekly from the admin panel, get warned when it's slipping, and
resolve it explicitly — and the client sees the promise and the live number on
every touchpoint.
