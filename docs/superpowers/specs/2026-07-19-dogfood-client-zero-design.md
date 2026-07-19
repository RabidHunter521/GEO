# Dogfood: SeenBy as Client #0 (Spec 5) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

If a prospect asks ChatGPT "best AI visibility agency in Malaysia" and SeenBy
doesn't appear, the pitch refutes itself. Conversely, a public, live SeenBy
scorecard — "here's our own AI visibility, measured by our own product, watch it
climb" — is the most credible marketing asset available, and it forces us to eat
our own toolkit (llms.txt, schema, content roadmap) before asking clients to.

This is 90% operational (create the client, run the playbook) and 10% product:
one flag so the internal client never pollutes real-client analytics.

## Decisions

- SeenBy is a **regular client row** (not a prospect): full scans, digests to
  ourselves, monthly PDF, share link. We experience exactly what clients do —
  that's the point (every rough edge found here is a retention fix).
- **`is_internal` flag** on `Client`, excluded from: the Visibility Index
  aggregates (Spec 4 — an agency bucket of ourselves is noise), revenue/pipeline
  rollups, and any cross-client stats. Included in everything else.
- **Public exposure = the existing share link.** No new public page; the
  marketing site links to `/view/[token]`. The share view is already whitelisted
  and client-safe — if it's good enough to publish to the world, it's good
  enough for clients, which is exactly the standard we want forced on us.

## Design

### 1. Product change (small)

- Migration: `Client.is_internal: bool` server_default false.
- Exclusions: Visibility Index derivation (Spec 4) filters `is_internal`;
  any portfolio/revenue rollup on `/clients` does the same. Grep-audit at
  implementation time for other cross-client aggregations.
- Admin UI: "Internal" badge on the client card + a checkbox in settings.

### 2. Operational runbook (checked into docs, not code)

`docs/dogfood-runbook.md`:
1. Create client: name SeenBy, industry "AI visibility agency" (or "marketing
   agency" — decide once; industry string feeds nothing once `is_internal`
   excludes us from the index), city KL, `is_internal=true`.
2. Track competitors: the local/regional agencies that appear for our queries
   (populates the war narrative for ourselves — we should feel the "Dr. Lim is
   winning" pressure too).
3. Run the full client playbook monthly: scan → action center → toolkit
   (seenby.my llms.txt/schema/robots, verified) → content roadmap → publish.
4. Put the share link on the marketing site ("Our own scorecard, live").
5. Treat every papercut found as a P1 retention bug — that's the real yield.

### 3. Success metric (business, not code)

Within 90 days, SeenBy is seen by AI for at least one recommendation-category
query ("best AI visibility agency Malaysia" family) on ≥2 platforms, with the
climb visible on the public scorecard.

## Scope boundaries

**In scope:** flag + migration + exclusions + badge; the runbook doc.
**Out of scope:** any bespoke public marketing page (the share view IS the
page); special-casing SeenBy anywhere else in code; automated posting of the
scorecard anywhere.

## Risks

- **Public scorecard shows a low score at first.** Feature, not bug — the climb
  is the story; an already-perfect score would look fake. If it stalls, that's
  the product telling us the playbook doesn't work, which we need to know before
  clients do.
- Forgetting the flag on creation → index pollution. Mitigation: index
  derivation also hard-excludes the SeenBy client by the flag, and the recompute
  job is idempotent — fixable retroactively by setting the flag and recomputing.

## Testing

- Index/rollup exclusion tests (internal client contributes to nothing
  cross-client); flag round-trips through settings; badge renders.

## Success criteria

SeenBy exists as client #0 with a public share link on the marketing site, is
invisible to all cross-client aggregates, and the monthly playbook is being run
on ourselves with the same artifacts clients get.
