# AI Referral Attribution — GA4 Auto-Ingest (Spec 3) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

The retention chart that matters most — *"AI sent you N visitors this month, up
X%"* — already exists in the product, but its input is **manual**:
`AiTrafficSnapshot` (`models/ai_traffic_snapshot.py`) is admin-entered monthly,
and everything downstream (`revenue_service.estimate_pipeline` /
`estimate_value_at_risk`, PDF, digest, client-view overview) already consumes it.
Manual entry means the number is late, error-prone, and skipped in busy months —
the churn-killer chart goes stale exactly when attention slips. This spec
automates the input via the GA4 Data API. Downstream changes: near zero.

## Decisions

- **Reuse `AiTrafficSnapshot` as the single sink.** GA4 sync upserts the same
  rows manual entry writes. One new `source` column ("manual" | "ga4")
  distinguishes them; a GA4 sync never silently overwrites a manual row and vice
  versa without admin confirmation.
- **Auth: one SeenBy service account.** Clients grant it Viewer on their GA4
  property (a 2-minute step in the onboarding checklist). No OAuth flow, no
  storing client credentials. Service-account JSON via env
  (`GA4_SERVICE_ACCOUNT_JSON`), same secrets pattern as other API keys.
- **Sync is admin-triggered first, scheduled later.** A "Sync traffic" button
  keeps MVP scope (on-demand philosophy); a monthly Celery task in
  `maintenance_tasks` is a one-line follow-up once trusted.
- **Phase B (lead attribution) is optional and separate** — shipped only after
  Phase A proves out.
- **Honesty rule:** referral attribution undercounts (dark traffic, app
  referrers). Every surface that shows the number keeps "at least / ~" framing.
  We never present it as a complete count.

## Design — Phase A (visitors)

### 1. Data model (one migration)

- `Client.ga4_property_id: str | None` — NULL = manual mode (unchanged behavior).
- `AiTrafficSnapshot.source: str` server_default `"manual"`.
- `AiTrafficSnapshot.breakdown: JSON | None` — per-referrer counts
  (e.g. `{"chatgpt.com": 140, "perplexity.ai": 61}`) for the drill-down.

### 2. Referrer classification

`AI_REFERRER_DOMAINS` in `core/constants.py`: chatgpt.com, chat.openai.com,
perplexity.ai, gemini.google.com, bard.google.com, copilot.microsoft.com,
claude.ai, you.com (extendable — constants only, no code change to add one).

### 3. Sync service

`ga4_traffic_service.py`:
- `sync_client_traffic(client_id, months_back=2)` — runs a GA4 Data API report:
  dimensions `sessionSource`/`pageReferrer` + month, metric `sessions`, filtered
  to `AI_REFERRER_DOMAINS`; aggregates per calendar month; upserts
  `AiTrafficSnapshot(period, ai_visitors, source="ga4", breakdown=...)`.
  Re-syncing the current month updates in place (GA4 data lags ~24-48h).
  `months_back=2` heals late-arriving data.
- Conflict rule: existing `manual` row for a period → skip and report
  ("manual value kept; delete it to let GA4 fill this month"). Existing `ga4`
  row → update.
- Failure isolation: API errors logged + surfaced to admin; never raises into a
  scan or report flow. Read scopes only.

### 4. Surfaces

- **Admin `/clients/[id]/settings`:** GA4 property ID field + connection state +
  "Sync traffic" button + last-sync timestamp/error.
- **Existing traffic surfaces (client view overview, PDF, digest):** unchanged —
  they read snapshots. One addition: where the monthly visitors number renders,
  show the per-platform breakdown when present ("ChatGPT 140 · Perplexity 61").
- `revenue_service` runs untouched — it already takes `ai_visitors`.

## Design — Phase B (leads, later)

- `AiTrafficSnapshot.ai_leads: int | None` — GA4 key events (form submit /
  click-to-call) from AI sources, same report pattern.
- Where set, report/digest show *actual* leads alongside the estimated pipeline
  ("6 enquiries came from AI visitors" vs. the modeled number). `estimate_*`
  stays as the model; actuals never overwrite estimates — they're shown together.
- Requires the client's GA4 to have key events configured — an onboarding
  checklist item, not a SeenBy feature.

## Scope boundaries

**In scope (A):** migration, constants, sync service, settings UI, breakdown
display, conflict rule.
**Out of scope:** OAuth per client; a SeenBy JS tracking snippet (parked — GA4
covers the 90% case); scheduled auto-sync (follow-up task once trusted);
Phase B until A proves out; any GEO-score influence (traffic stays informational
— the model's docstring rule stands).

## Risks

- Clients without GA4 (or unwilling to grant access) → manual mode remains fully
  supported; no regression.
- GA4 referrer exclusions/misconfig can zero the numbers → settings page shows
  last-sync diagnostics; docs include the "check referral exclusion list" step.
- Google API quota/deps: `google-analytics-data` client added to backend deps;
  quota is trivial at ≤10 clients/monthly pulls.

## Testing

- Classification: referrer → platform mapping incl. subdomains and unknowns.
- Upsert: ga4-over-ga4 updates; ga4-vs-manual skips; months_back window.
- Service errors: API failure surfaces to admin, never propagates.
- Surfaces: breakdown renders when present, absent otherwise; "~/at least"
  framing on client-facing copy; sanitizer green.

## Success criteria

Faris connects a client's GA4 in settings once; every month the AI-visitor
number and per-platform breakdown appear on the portal, PDF, and digest without
manual entry, and the revenue math downstream keeps working unchanged.
