# SeenBy Benchmark and Data Moat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn SeenBy's normalized, multi-industry evidence into privacy-safe comparative intelligence and a compounding Southeast Asia GEO/AEO data advantage.

**Architecture:** Build versioned cohort definitions over the shared horizontal data model, aggregate only eligible clients into immutable benchmark snapshots, and expose percentile/range comparisons through whitelisted APIs. Publish a separately reviewed aggregate index from the same snapshot layer; never query identifiable client rows from a public endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL/Supabase, Pydantic, pytest, Next.js 15, React 19, TypeScript, Vitest

## Global Constraints

- Requires Phases 0–5 and sufficient comparable historical data.
- Keep healthcare, F&B, and local services on the same benchmark engine; industry packs provide dimensions and labels, not separate data silos.
- Default minimum eligible cohort size is 10 organizations; configurable only upward in production.
- Suppress a metric when fewer than 5 members contribute a non-null value, even if the cohort itself is eligible.
- Exclude test, demo, trial, internal, opted-out, and poor-measurement-coverage clients.
- Never return client IDs, domains, names, locations, query text, small geography cells, or reconstructable combinations.
- Benchmarks compare like with like: pack, market, period, organization/location scale, query coverage, and calculation version.
- New tables must enable RLS, revoke anonymous access, use explicit policies, and index policy/filter columns.
- Public index output comes only from approved immutable snapshots.
- A benchmark is descriptive, not a performance guarantee.
- Use `rtk` for repository commands and TDD for production changes.

---

### Task 1: Persist cohorts, membership, and immutable snapshots

**Files:**
- Create: `backend/app/models/benchmark_cohort.py`
- Create: `backend/app/models/benchmark_snapshot.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/e2b8d6a5f1c3_add_benchmark_data_moat.py`
- Create: `backend/tests/test_benchmark_models.py`
- Create: `backend/tests/test_benchmark_migration.py`

**Produces:** Versioned cohort definitions, private eligibility membership, and immutable aggregate results.

- [ ] **Step 1: Write failing model and migration tests**

Define:

```python
class BenchmarkCohort:
    id: UUID
    cohort_key: str
    definition_version: str
    industry_pack: str
    subcategory: str | None
    country_code: str
    market_area: str | None
    scale_band: str
    coverage_band: str
    period_type: str
    min_member_count: int
    is_active: bool

class BenchmarkSnapshot:
    id: UUID
    cohort_id: UUID
    period_start: date
    period_end: date
    metric_key: str
    calculation_version: str
    eligible_member_count: int
    contributing_member_count: int
    p25: Decimal | None
    p50: Decimal | None
    p75: Decimal | None
    mean: Decimal | None
    suppressed: bool
    generated_at: datetime
    approved_at: datetime | None
```

Use a separate private `benchmark_cohort_memberships` table with `client_id`, inclusion status, exclusion reason, measurement coverage, and evaluation time. Never expose membership through client or public schemas.

- [ ] **Step 2: Implement revision `e2b8d6a5f1c3`**

Set `down_revision = "d1a7c5f4e0b2"`. Add:

```sql
UNIQUE (cohort_key, definition_version)
UNIQUE (cohort_id, client_id, evaluation_period_start, evaluation_period_end)
UNIQUE (cohort_id, period_start, period_end, metric_key, calculation_version)
INDEX  (industry_pack, country_code, scale_band, is_active)
INDEX  (client_id, evaluation_period_end DESC)
INDEX  (cohort_id, period_end DESC, metric_key)
```

Enable RLS and revoke `anon` on all three tables. Membership is service-role/admin only. Snapshot reads require authenticated access until a separate publication record explicitly approves them.

- [ ] **Step 3: Prove immutability**

Add a database trigger or repository-enforced rule that rejects updates to approved snapshots. Corrections create a new calculation version or replacement snapshot; they never mutate published values.

- [ ] **Step 4: Verify migration reversibility**

```bash
cd backend
rtk alembic upgrade head
rtk pytest tests/test_benchmark_models.py tests/test_benchmark_migration.py -q
rtk alembic downgrade d1a7c5f4e0b2
rtk alembic upgrade head
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/models/benchmark_cohort.py backend/app/models/benchmark_snapshot.py backend/app/models/__init__.py backend/alembic/versions/e2b8d6a5f1c3_add_benchmark_data_moat.py backend/tests/test_benchmark_models.py backend/tests/test_benchmark_migration.py
rtk git commit -m "feat: add privacy-safe benchmark storage"
```

---

### Task 2: Build deterministic cohort eligibility

**Files:**
- Create: `backend/app/schemas/benchmark_cohort.py`
- Create: `backend/app/services/benchmark_cohort_service.py`
- Create: `backend/tests/test_benchmark_cohort_service.py`

**Produces:** Explainable inclusion/exclusion using comparable company and measurement attributes.

- [ ] **Step 1: Write failing eligibility tests**

Cover pack, subcategory, country, market area, location-count band, query-coverage band, data freshness, measurement version, client opt-out, and test/demo exclusion. Assert that missing data leads to a documented exclusion or broader eligible cohort—not invented classification.

- [ ] **Step 2: Implement versioned banding**

```python
SCALE_BANDS = {
    "single_location": range(1, 2),
    "small_multi_location": range(2, 6),
    "large_multi_location": range(6, 10_000),
}

COVERAGE_BANDS = {
    "starter": (10, 29),
    "standard": (30, 99),
    "deep": (100, 10_000),
}
```

Keep thresholds in a versioned configuration object. Return `eligible`, `cohort_key`, and machine-readable `reason_codes`.

- [ ] **Step 3: Add safe fallback logic**

When a narrow cohort is below threshold, widen one dimension at a time in this order:

1. remove subcategory;
2. widen market area to country;
3. merge adjacent scale bands;
4. stop and suppress.

Never cross industry-pack boundaries or countries merely to produce a number.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_benchmark_cohort_service.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/benchmark_cohort.py backend/app/services/benchmark_cohort_service.py backend/tests/test_benchmark_cohort_service.py
rtk git commit -m "feat: calculate benchmark eligibility"
```

---

### Task 3: Generate privacy-safe benchmark snapshots

**Files:**
- Create: `backend/app/services/benchmark_snapshot_service.py`
- Create: `backend/app/tasks/benchmark_tasks.py`
- Modify: `backend/app/services/benchmark_service.py`
- Create: `backend/tests/test_benchmark_snapshot_service.py`
- Create: `backend/tests/test_benchmark_privacy.py`

**Produces:** Scheduled percentile aggregates with suppression, clipping, and full lineage.

- [ ] **Step 1: Write failing aggregation and privacy tests**

Test median and percentile calculation, null contributors, minimum cohort size, minimum contributing size, outlier clipping, snapshot idempotency, mixed calculation versions, and approved-snapshot immutability.

Add differencing-attack tests: overlapping cohort requests must not reveal a single member by subtraction. Block arbitrary user-selected filters.

- [ ] **Step 2: Define the initial metric registry**

```python
BENCHMARK_METRICS = {
    "ai_presence_score": {"source": "geo_scores", "clip": (0, 100)},
    "answer_stability_score": {"source": "query_stability", "clip": (0, 100)},
    "accuracy_rate": {"source": "truth_comparisons", "clip": (0, 1)},
    "citation_share": {"source": "scan_query_sources", "clip": (0, 1)},
    "verified_action_rate": {"source": "outcome_actions", "clip": (0, 1)},
}
```

Do not benchmark estimated revenue in the first release. Metric definitions include unit, calculation version, minimum coverage, and allowed packs.

- [ ] **Step 3: Implement snapshot generation**

Read through explicit aggregate queries, clip values using registry limits, compute aggregates in one transaction, record input period/version/member counts, and write a new immutable snapshot. Log exclusions by reason without logging client identities in shared operational logs.

- [ ] **Step 4: Add scheduled execution**

Generate monthly operational benchmarks after period close. A rerun with the same version is idempotent; a logic change requires a new calculation version.

- [ ] **Step 5: Verify**

```bash
cd backend
rtk pytest tests/test_benchmark_snapshot_service.py tests/test_benchmark_privacy.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/services/benchmark_snapshot_service.py backend/app/tasks/benchmark_tasks.py backend/app/services/benchmark_service.py backend/tests/test_benchmark_snapshot_service.py backend/tests/test_benchmark_privacy.py
rtk git commit -m "feat: generate private benchmark snapshots"
```

---

### Task 4: Expose client-safe benchmark comparisons

**Files:**
- Create: `backend/app/schemas/benchmark_comparison.py`
- Create: `backend/app/services/benchmark_comparison_service.py`
- Create: `backend/app/api/v1/benchmarks.py`
- Modify: `backend/app/api/v1/client_view.py`
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_benchmark_comparison_service.py`
- Create: `backend/tests/test_api_benchmarks.py`
- Modify: `backend/tests/test_api_client_view.py`

**Produces:** Whitelisted percentile/range comparisons for admins and share-link clients.

- [ ] **Step 1: Write failing response-contract tests**

An eligible comparison returns:

```python
class BenchmarkComparison:
    metric_key: str
    client_value: float
    percentile_band: str
    cohort_label: str
    p25: float
    p50: float
    p75: float
    period_end: date
    member_count_band: str
    calculation_version: str
    caveat: str
```

Return member-count bands such as `10–19` or `20–49`, never exact counts. Suppressed comparisons return a reason and no aggregate values.

- [ ] **Step 2: Implement comparison service**

Select only approved snapshots, match calculation versions, and calculate a coarse percentile band (`bottom_quartile`, `middle_half`, `top_quartile`). Do not return exact ranks.

- [ ] **Step 3: Add endpoints**

```text
GET /clients/{client_id}/benchmarks
GET /view/{token}/benchmarks
```

The public endpoint is rate-limited, non-indexable, and uses a purpose-built schema with no cohort IDs, internal definitions, or membership details.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_benchmark_comparison_service.py tests/test_api_benchmarks.py tests/test_api_client_view.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/benchmark_comparison.py backend/app/services/benchmark_comparison_service.py backend/app/api/v1/benchmarks.py backend/app/api/v1/client_view.py backend/app/schemas/client_view.py backend/app/api/v1/router.py backend/tests/test_benchmark_comparison_service.py backend/tests/test_api_benchmarks.py backend/tests/test_api_client_view.py
rtk git commit -m "feat: expose cohort benchmark comparisons"
```

---

### Task 5: Add portfolio intelligence for SeenBy operators

**Files:**
- Create: `frontend/src/components/benchmarks/PortfolioBenchmarkGrid.tsx`
- Create: `frontend/src/components/benchmarks/CohortHealthPanel.tsx`
- Create: `frontend/src/app/benchmarks/page.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/components/benchmarks/PortfolioBenchmarkGrid.test.tsx`

**Produces:** An internal portfolio view of cohort health, client opportunity, and data coverage.

- [ ] **Step 1: Write failing component tests**

Cover suppressed cells, stale snapshots, calculation-version mismatch, broad-cohort fallback, empty state, keyboard navigation, and 360px responsive behavior.

- [ ] **Step 2: Implement the portfolio view**

Show:

- eligible client count by pack and market;
- data coverage and freshness;
- cohort suppression rate;
- median and interquartile range by metric;
- clients below cohort range as an opportunity queue;
- no individual competitor identity.

- [ ] **Step 3: Integrate with grouped navigation**

Place Benchmarks under Intelligence in the Phase 1 navigation. Keep existing `IndustryBenchmarkCard` working until the new route is proven; migrate it to the new API only after response-contract tests pass.

- [ ] **Step 4: Verify**

```bash
cd frontend
rtk npm test -- --run src/components/benchmarks/PortfolioBenchmarkGrid.test.tsx
rtk npm run typecheck
rtk npm run build
```

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/benchmarks/PortfolioBenchmarkGrid.tsx frontend/src/components/benchmarks/CohortHealthPanel.tsx frontend/src/app/benchmarks/page.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/lib/api.ts frontend/src/types/index.ts frontend/src/components/benchmarks/PortfolioBenchmarkGrid.test.tsx
rtk git commit -m "feat: add portfolio benchmark intelligence"
```

---

### Task 6: Present benchmark context in the client experience

**Files:**
- Modify: `frontend/src/components/IndustryBenchmarkCard.tsx`
- Create: `frontend/src/components/benchmarks/ClientBenchmarkCard.tsx`
- Modify: `frontend/src/lib/view-api.ts`
- Modify: `frontend/src/app/view/[token]/page.tsx`
- Create: `frontend/src/components/benchmarks/ClientBenchmarkCard.test.tsx`

**Produces:** Plain-language comparisons without exposing peers or implying guarantees.

- [ ] **Step 1: Write failing client-view tests**

Assert that the component:

- says “among comparable SeenBy clients,” not “your competitors”;
- shows period, cohort label, and range;
- hides suppressed values;
- never shows exact member count or rank;
- distinguishes “not enough comparable data” from poor performance;
- renders at 360px and by keyboard.

- [ ] **Step 2: Implement client-safe presentation**

Lead with the client's position band and one next action. Put methodology and caveats behind progressive disclosure. Never display an estimated revenue benchmark.

- [ ] **Step 3: Replace legacy card data only after parity**

Keep the current card behind a feature flag until the new endpoint supplies an approved snapshot for that client. The fallback must not synthesize a cohort from hard-coded industry values.

- [ ] **Step 4: Verify**

```bash
cd frontend
rtk npm test -- --run src/components/benchmarks/ClientBenchmarkCard.test.tsx
rtk npm run typecheck
```

- [ ] **Step 5: Commit**

```bash
rtk git add frontend/src/components/IndustryBenchmarkCard.tsx frontend/src/components/benchmarks/ClientBenchmarkCard.tsx frontend/src/lib/view-api.ts frontend/src/app/view/[token]/page.tsx frontend/src/components/benchmarks/ClientBenchmarkCard.test.tsx
rtk git commit -m "feat: add client-safe benchmark context"
```

---

### Task 7: Build the Southeast Asia AI Visibility Index publication layer

**Files:**
- Create: `backend/app/models/benchmark_publication.py`
- Create: `backend/app/schemas/benchmark_publication.py`
- Create: `backend/app/services/benchmark_publication_service.py`
- Create: `backend/app/api/v1/public_benchmarks.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/alembic/versions/e2b8d6a5f1c3_add_benchmark_data_moat.py`
- Create: `backend/tests/test_benchmark_publication_service.py`
- Create: `backend/tests/test_api_public_benchmarks.py`

**Produces:** Reviewable, immutable aggregate datasets for a quarterly SEA AI Visibility Index.

- [ ] **Step 1: Write failing publication tests**

A publication must reference approved snapshots and include:

```python
slug
title
edition
methodology_version
period_start
period_end
status  # draft, approved, published, withdrawn
approved_by
approved_at
published_at
payload_hash
```

Test minimum cohort/contributor thresholds again at publication time, withdrawal behavior, immutable approved payloads, and no client identifiers in serialized JSON.

- [ ] **Step 2: Extend the Phase 6 migration**

Create `benchmark_publications` with RLS and keep direct anonymous database
grants revoked. Anonymous users read published payloads only through the
rate-limited FastAPI server endpoint. Draft/approval actions remain
authenticated and audited.

- [ ] **Step 3: Implement human-reviewed publication workflow**

```text
POST /benchmarks/publications
POST /benchmarks/publications/{id}/approve
POST /benchmarks/publications/{id}/publish
POST /benchmarks/publications/{id}/withdraw
GET  /public/benchmarks/{slug}
```

Require different actor IDs for generation and approval in production. Publishing never recalculates; it promotes a hashed, reviewed payload.

- [ ] **Step 4: Define the first edition**

Use only metrics that pass coverage and privacy gates across at least healthcare, F&B, and local services. Report regional/industry ranges, source-domain influence, AI presence, stability, accuracy, and verified-action rate. Exclude small-market cuts and business-value estimates.

- [ ] **Step 5: Verify**

```bash
cd backend
rtk pytest tests/test_benchmark_publication_service.py tests/test_api_public_benchmarks.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/models/benchmark_publication.py backend/app/schemas/benchmark_publication.py backend/app/services/benchmark_publication_service.py backend/app/api/v1/public_benchmarks.py backend/app/api/v1/router.py backend/alembic/versions/e2b8d6a5f1c3_add_benchmark_data_moat.py backend/tests/test_benchmark_publication_service.py backend/tests/test_api_public_benchmarks.py
rtk git commit -m "feat: add benchmark publication workflow"
```

---

### Task 8: Add aggregate source and demand intelligence

**Files:**
- Create: `backend/app/schemas/market_intelligence.py`
- Create: `backend/app/services/market_intelligence_service.py`
- Create: `backend/app/api/v1/market_intelligence.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_market_intelligence_service.py`
- Create: `backend/tests/test_api_market_intelligence.py`

**Produces:** Privacy-safe trends that improve strategy, pack quality, and query selection.

- [ ] **Step 1: Write failing aggregation tests**

Cover domain normalization, source influence by model/pack/market, query-intent demand, seasonal windows, minimum cohorts, dominant-client suppression, and no raw prompt output.

- [ ] **Step 2: Implement approved aggregates**

Return only:

```text
source domain category and influence band
intent category and demand band
pack and country
period
sample/member count bands
calculation version
```

Suppress any cell where one client supplies more than 20% of observations or the minimum-member rule fails.

- [ ] **Step 3: Add authenticated endpoints**

```text
GET /market-intelligence/source-influence
GET /market-intelligence/query-demand
```

These endpoints are internal in the first release. Public publication requires the Task 7 review workflow.

- [ ] **Step 4: Feed learnings back into packs**

Export reviewed aggregate signals to the pack registry as candidate updates. A human must approve a pack-version change; benchmark output never edits prompts or risk rules automatically.

- [ ] **Step 5: Verify**

```bash
cd backend
rtk pytest tests/test_market_intelligence_service.py tests/test_api_market_intelligence.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/schemas/market_intelligence.py backend/app/services/market_intelligence_service.py backend/app/api/v1/market_intelligence.py backend/app/api/v1/router.py backend/tests/test_market_intelligence_service.py backend/tests/test_api_market_intelligence.py
rtk git commit -m "feat: add aggregate market intelligence"
```

---

### Task 9: Run the Phase 6 privacy and release gate

**Files:**
- Create: `docs/ops/benchmark-privacy-runbook.md`
- Modify: `docs/ops/release-checklist.md`

**Produces:** A benchmark release that is reproducible, privacy-tested, and operationally reversible.

- [ ] **Step 1: Document governance**

Document cohort versions, opt-out handling, minimum thresholds, suppression, dominant-client rules, approval separation, snapshot replacement, incident withdrawal, retention, and rollback to `d1a7c5f4e0b2`.

- [ ] **Step 2: Run backend verification**

```bash
cd backend
rtk alembic upgrade head
rtk pytest tests/test_benchmark_models.py tests/test_benchmark_migration.py tests/test_benchmark_cohort_service.py tests/test_benchmark_snapshot_service.py tests/test_benchmark_privacy.py tests/test_benchmark_comparison_service.py tests/test_api_benchmarks.py tests/test_api_client_view.py tests/test_benchmark_publication_service.py tests/test_api_public_benchmarks.py tests/test_market_intelligence_service.py tests/test_api_market_intelligence.py -q
```

- [ ] **Step 3: Run frontend and repository verification**

```bash
cd frontend
rtk npm test -- --run
rtk npm run typecheck
rtk npm run build
cd ..
rtk git diff --check
```

- [ ] **Step 4: Prove privacy controls**

Using non-owner and anonymous test roles, verify RLS on every Phase 6 table. Attempt narrow, overlapping, and repeated cohort queries. Confirm suppression, rate limits, count banding, and absence of client identifiers in admin, client-view, and public payloads.

- [ ] **Step 5: Inspect query plans and job recovery**

Run `EXPLAIN (ANALYZE, BUFFERS)` for cohort eligibility, snapshot lookup, and client comparison queries. Interrupt and rerun snapshot generation to prove idempotency and verify that an approved snapshot remains immutable.

- [ ] **Step 6: Complete a three-pack acceptance test**

Generate eligible or correctly suppressed cohorts for healthcare, F&B, and local services; view one client comparison; approve and publish one synthetic index edition; withdraw it; confirm public access closes without deleting the audit record.

- [ ] **Step 7: Commit**

```bash
rtk git add docs/ops/benchmark-privacy-runbook.md docs/ops/release-checklist.md
rtk git commit -m "docs: add benchmark privacy release gate"
```
