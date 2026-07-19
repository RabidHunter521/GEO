# Pitch Mode — Live 3-Query Roast (Spec 6) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

The strongest sales moment SeenBy can produce is live, in the meeting: type in
the prospect's clinic, and within a minute show ChatGPT recommending their rival
by name, on screen. All the machinery exists — prospect clients (`is_prospect`),
the scan engine, brand detection, verbatim proof cards. What's missing is a
**fast path** (3 queries, 2 platforms, ~30-60s instead of a full multi-minute
scan) and a **presentation-grade view** (big type, one answer per screen — not
an admin table). The self-serve audit funnel (feature-ideas #20) is the passive
version; this is the active weapon, and most of it is reuse.

## Decisions

- **Pitch scan = a real `Scan` with a flag**, not a new subsystem. It reuses
  `scan_service.run_scan` with a query-limiting parameter; results land in
  `ScanQueryResult` like any scan, so proof cards and evidence views work as-is.
- **Excluded from history and score.** A 3-query scan would corrupt the
  visibility trend and score series. `Scan.is_pitch: bool` (server_default
  false) and every trend/score/history consumer filters it out. Same invariant
  pattern as Spec 1's control exclusion.
- **Fixed recipe:** 1 recommendation + 1 local + 1 brand query, on **chatgpt +
  gemini** (the two names prospects recognize; halves the wait). Recipe in
  constants (`PITCH_SCAN_RECIPE`), not hardcoded in the service.
- **Admin-only surface.** This is Faris presenting from his laptop — not a
  public tool, no share token. (The public funnel version is a separate, later
  spec.)
- **No new LLM calls beyond the scan itself.** The verdict copy is
  deterministic from `brand_detected` + detected competitor names.

## Design

### 1. Backend

- Migration: `Scan.is_pitch` bool, server_default false.
- `scan_service.run_scan` gains an optional `pitch: bool = False` (or a thin
  `run_pitch_scan` wrapper): builds only the recipe's 3 queries (query_builder
  gets a recipe-subset mode), runs on the recipe platforms ∩ enabled platforms,
  skips post-commit heavies that don't serve a pitch (action center, provenance
  enrichment) but keeps brand/competitor detection. Alerting skipped
  (`is_pitch` guard) — no score-drop alarms from a 3-query run.
- Exclusion filters: score history, visibility trend, win/loss, diff/flip
  detection, digest/report data gathering all ignore `is_pitch` scans.
  Regression test per consumer (mirror of Spec 1's invariant tests).
- Endpoint: `POST /api/v1/scans/pitch` (client_id) → scan id; existing scan
  status polling reused.

### 2. Frontend — presentation view

New admin route `/clients/[id]/pitch`:
- **Run state:** one button ("Run live scan"), progress with per-query ticks —
  the audience watches it happen (the theater is part of the pitch).
- **Result state:** one full-screen card per query (large type, keyboard/swipe
  navigation): the query as asked, the platform, the verdict — *"Seen by AI"* /
  *"Not seen by AI"* — and the verbatim answer snippet with the prospect's brand
  (if present) and competitor names highlighted. Competitor names are NOT
  redacted: this is an admin surface, and naming the rival is the entire point.
- **Closing card:** deterministic summary — "{Rival} was seen by AI {n} of
  {total} times. {Prospect} was seen {m} of {total}." + a "book the audit" line.
- Reuses proof-card/snippet componentry where practical; presentation styling
  (dark, large, minimal chrome) within shadcn constraints.

### 3. Flow

Prospect row (created in ~60s: name, website, industry, city, 1-2 competitors)
→ `/clients/[id]/pitch` → run → present → later, "Convert to Client" as usual.
If a full scan already exists, the pitch page offers "present latest results"
without re-running (uses the newest scan's rows for the recipe categories).

## Scope boundaries

**In scope:** `is_pitch` flag + migration, recipe constant, fast-path scan,
exclusion filters + tests, pitch endpoint, presentation route.
**Out of scope:** public self-serve funnel; PDF export of the pitch (screenshot
suffices); any use of pitch scans in score/trend/index (explicitly excluded —
also excluded from Spec 4's Index derivation); multi-language recipes (Spec 7
can extend the recipe later).

## Risks

- **Live-demo risk:** a platform hiccup mid-meeting. Mitigations: 2-platform
  recipe with the existing per-platform isolation (one failing platform still
  yields the other's cards), the "present latest results" fallback, and the
  existing retry-once semantics.
- **The roast can backfire** — the prospect might be seen everywhere. The
  closing card handles it honestly: strong visibility → the pitch pivots to
  "keep it that way / your competitor is next" (Faris's script, not code).
- Cost per pitch: 6 API calls — negligible; budget_service applies as usual.

## Testing

- Recipe subset built correctly; platforms intersected with enabled set.
- `is_pitch` exclusion invariants across every trend/score/history consumer.
- Alert + action-center skip on pitch scans.
- Presentation route: verdict copy matches `brand_detected`; competitor
  highlighting; graceful single-platform render when one platform failed.

## Success criteria

From a blank prospect to rival-on-screen in under 3 minutes on a live
connection, with zero contamination of any score, trend, alert, or index — and
the whole thing runs off the existing scan engine.
