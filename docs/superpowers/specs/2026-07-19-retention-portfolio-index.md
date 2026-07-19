# Retention & Premium Portfolio — Spec Index

**Date:** 2026-07-19 (specs); plans written same day via superpowers:writing-plans.
**Status:** Every spec now has an implementation plan at
`docs/superpowers/plans/2026-07-19-<name>.md` (same basename, no `-design`).
Specs were code-grounded during planning; two were revised: spec 4 gained a
"Current State" section (the existing `benchmark_service` peer percentile is
extended, not duplicated) and its derivation now names the cross-spec
exclusions (`is_pitch`, `is_internal`, controls). Each plan ends with a
self-review noting any deviations from its spec. Remaining before code:
a Faris review pass per spec/plan, then execute via
superpowers:subagent-driven-development, one plan per feature branch.

Context: brainstorm 2026-07-19 ("YC skeptic" session). Declared constraint: **retention
is the current bottleneck**, not new-client acquisition. These specs are the "features
I'd actually fund" list, sequenced for retention first. They sit AROUND the committed
5-phase GEO roadmap (see memory `seenby-geo-endtoend-roadmap`) — that roadmap remains
the base layer and is not displaced by anything here.

## The specs

| # | Spec file | One-liner | Size |
|---|---|---|---|
| 0 | `2026-07-19-retention-narrative-fixes-design.md` | Ship the "here's why" that's already computed but never reaches the client | S |
| 1 | `2026-07-19-control-query-causality-design.md` | Untouched benchmark queries → causal proof the work moved the number | M |
| 2 | `2026-07-19-guarantee-engine-design.md` | Baseline → target → deadline commitment, tracked on every surface | M |
| 3 | `2026-07-19-ai-referral-attribution-design.md` | GA4 auto-ingest of AI-referral visitors (upgrade manual snapshots) | M |
| 4 | `2026-07-19-visibility-index-design.md` | Anonymized cross-client benchmark aggregates — the compounding data asset | M |
| 5 | `2026-07-19-dogfood-client-zero-design.md` | SeenBy as client #0, `is_internal` flag, public living case study | S |
| 6 | `2026-07-19-pitch-mode-design.md` | 3-query live "roast" scan + presentation view for sales meetings | M |
| 7 | `2026-07-19-multilanguage-scans-design.md` | BM + Chinese query sets (amends CLAUDE.md §11 exclusion — needs sign-off) | L |
| 8 | `2026-07-19-misinformation-compliance-design.md` | Medical AI-misinformation findings + correction loop (Premium anchor) | L |

## Recommended build order (retention-first)

1. **Spec 0** — days of work, pure leverage: existing evidence finally reaches clients.
2. **Spec 1** — causal proof; every later report gets stronger. Start early because
   proof needs months of history to be persuasive.
3. **Spec 3** — automated AI-traffic numbers; churn-killer chart.
4. **Spec 2** — guarantee engine; only credible once 1 + 3 exist.
5. **Spec 6, 5** — sales weapons (pitch mode, dogfooding). Cheap, do when a pitch is near.
6. **Spec 4** — start the aggregation job EARLY (it only needs the maintenance task),
   even if the admin UI comes much later — the data asset compounds with every scan.
7. **Spec 7, 8** — moat + Premium deepeners. Spec 8 can jump the queue if a clinic
   deal needs the misinformation-protection anchor to close.

## Cross-cutting dependencies & decisions needed from Faris

- **Spec 7 requires amending CLAUDE.md §11** ("multi-locale prompts" is currently a
  stop-and-confirm exclusion). Explicit sign-off needed before any code.
- **Spec 8's Premium gating depends on the parked `corepremium.md` plan column** —
  spec 8 is written to work ungated first, gate later.
- **Prompt-audit fix first:** the 2026-07 prompt audit (docs/prompt-audit-2026-07.md)
  found assessment prompts fabricating "public evidence". Every spec here that adds a
  client-facing claim (0, 2, 8 especially) assumes that trust problem gets fixed.
  Nothing below ships a claim without verbatim stored evidence behind it.
- No spec here bumps SCORE_VERSION. Anything that would change the score formula
  (notably spec 7's language handling) is explicitly designed NOT to.
