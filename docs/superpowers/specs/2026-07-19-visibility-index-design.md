# SeenBy AI Visibility Index (Spec 4) — Design Spec

**Date:** 2026-07-19
**Status:** Draft — pending Faris review, then writing-plans
**Author:** Faris + Claude

## Problem

Every scan SeenBy runs — clients, prospects, competitors — produces market data
nobody else in Malaysia has: how often AI recommends businesses of a given
industry in a given place. Today that data evaporates into per-client views.
Aggregated, it becomes three assets at once: (a) the Premium-tier benchmark
percentile already promised in `corepremium.md` ("you're seen 61% of the time;
the median KL dental clinic is at 34%"), (b) quarterly public "SeenBy AI
Visibility Index — Malaysia" content that makes SeenBy the cited authority
(our own GEO play), and (c) a moat: features can be copied, 18 months of
Malaysian scan history cannot. The asset compounds with every scan — **the
aggregation must start now**, even if UI ships much later.

## Current State (verified 2026-07-19)

`backend/app/services/benchmark_service.py` ALREADY implements a same-industry
peer percentile: latest GeoScore per non-archived, non-prospect client,
case-insensitive industry match, hidden below `MIN_BENCHMARK_PEERS = 3`
(constants.py:117), surfaced via `IndustryBenchmarkResponse`. The Index does
NOT replace it. What benchmark_service cannot do — and what this spec adds:
(a) **history** (it computes live from latest scores only; no month-over-month
record survives), (b) **visibility-frequency buckets by industry × region ×
platform** (it compares overall GEO score only, no region/platform cut),
(c) **market data beyond paying clients** (it excludes prospects by design;
the Index deliberately includes prospects + competitor rows as market
observations), (d) **export** for the public quarterly report.
`compute_percentile` and `MIN_BENCHMARK_PEERS` are reused as-is.

## Decisions

- **Aggregate from day one, publish only above a threshold.** Snapshots are
  computed and stored regardless of sample size; anything client- or public-
  facing requires ≥3 distinct businesses in the bucket (small-N shows a
  misleading and potentially identifying "average").
- **Prospects and competitor query rows count as market data.** A prospect scan
  and a competitor's brand-visibility row are observations of the market. This
  widens N far beyond the paying-client count.
- **Anonymized aggregates only, ever.** Snapshots store counts and averages —
  no business names, no client IDs in anything that leaves the admin panel.
- **Buckets:** (industry, state-or-country, platform, month). Industry is the
  free-text `Client.industry` — normalization needed (see Risks).

## Design

### 1. Data model (one migration)

`backend/app/models/index_snapshot.py`:

```
IndexSnapshot: id, industry (normalized str), region (str), platform (str),
               period (date, first of month),
               business_count (int), query_count (int),
               visibility_frequency (numeric 0-100, avg across businesses),
               avg_recommendation_position (numeric|None),
               computed_at
UniqueConstraint(industry, region, platform, period)
```

Derivation, per business in the bucket: visibility frequency = share of its
brand-relevant result rows (client-owned rows for clients/prospects; a
competitor's own rows for competitors) with `brand_detected=True`, from scans
completed in the period. Excluded from derivation: control rows (Spec 1),
pitch scans (Spec 6 `is_pitch`), and internal clients (Spec 5 `is_internal`) —
each exclusion applies once its spec ships. Bucket value =
unweighted mean across businesses (each business counts once, regardless of
scan count).

### 2. Aggregation job

`index_service.compute_period(period)` — idempotent recompute of all buckets for
a month; wired as a monthly `maintenance_tasks` Celery task plus an admin
"recompute" trigger. Backfill: run once over historical scans at ship time
(booleans survive the 90-day raw-response purge, so full scan history is usable).

### 3. Industry normalization

`INDUSTRY_ALIASES` map in constants ("dental clinic", "dentist" → "dental");
unmatched industries pass through lowercased. Admin page shows bucket keys so
Faris can spot and merge strays by extending the alias map (data fix = constants
edit + recompute).

### 4. Surfaces

| Surface | Content | Gate |
|---|---|---|
| Admin `/clients/gap-matrix` or new admin index page | Bucket table: industry × region × platform trend, N per bucket | none (admin sees all) |
| Client view overview — benchmark card | *"Businesses like yours in {region} are seen by AI {X}% of the time. You: {Y}%."* + percentile | `business_count ≥ 3` AND Premium plan (per `corepremium.md`; ships ungated until the plan column exists) |
| Monthly PDF | Same benchmark line in the score section | same gate |
| Public quarterly report | Manual: admin export (CSV/JSON of qualifying buckets) → Faris writes the report. No public web endpoint in this spec. | export requires ≥3, admin-only |

Client-facing copy uses approved vocabulary only ("seen by AI", "visibility
frequency"). The comparison never names any other business.

## Scope boundaries

**In scope:** model + migration, aggregation service + monthly task + backfill,
alias normalization, admin bucket view, gated benchmark card (client view +
PDF), admin export.
**Out of scope:** public API/web page for the index (quarterly report is a
manual content play); per-competitor named benchmarks; weighting by query
volume; multi-country expansion logic.

## Risks

- **Tiny N at the start** — most buckets won't clear the threshold for months.
  Fine: the point of shipping the job early is that the asset accrues silently;
  the benchmark card simply doesn't render yet.
- **Bucket drift from free-text industry** — mitigated by alias map + admin
  visibility of stray keys; worst case is an unmerged bucket, not wrong data.
- **Cross-client data use** — aggregates only; add a line to the engagement
  letter/T&Cs noting anonymized benchmarking (business decision, flagged here).
- Query-mix bias (different clients run different query sets) — accepted for v1;
  the unweighted per-business mean bounds any single business's influence.

## Testing

- Derivation: per-business frequency correct; competitor rows attributed to the
  competitor, not the client; controls excluded; each business counted once.
- Idempotency: recompute of a period replaces, never duplicates.
- Threshold: card/export absent below N=3; percentile math at boundaries.
- Anonymity: no name/ID fields in any non-admin payload (schema test).

## Success criteria

The monthly job has been quietly building buckets from every scan; the first
time a bucket crosses N=3, the Premium benchmark line lights up on that client's
portal and PDF with real market context — and Faris can export a defensible
dataset for the first public "SeenBy AI Visibility Index" post.
