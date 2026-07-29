# SeenBy Measurement and Business Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SeenBy's visibility claims repeatable and connect observed AI discovery to defensible business outcomes without presenting modeled impact as measured revenue.

**Architecture:** Persist a governed query universe, sample high-value prompts repeatedly, and calculate stability independently from the existing point-in-time score. Normalize Search Console and conversion evidence into tenant-scoped records, then expose an evidence ladder—observed, attributed, assisted, estimated—through separate admin and client-safe response models.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL/Supabase, Pydantic, pytest, Next.js 15, React 19, TypeScript, Vitest

## Global Constraints

- Requires Phases 0–4 and their data contracts to be complete.
- Preserve current `ControlQuery`, `Scan`, `ScanQueryResult`, `AiTrafficSnapshot`, score, and report history.
- Treat the existing score as a snapshot; never silently redefine it as a stability score.
- Every money value must carry currency, evidence level, calculation version, and time window.
- Label estimates as estimates in database records, APIs, reports, and UI.
- Never claim causality from correlation, referral traffic, or rank movement alone.
- New tables must enable RLS, revoke anonymous access, use explicit tenant policies, and index tenant/time and policy columns.
- The service-role credential remains backend-only.
- Store normalized facts, not raw OAuth tokens or full third-party payloads.
- Repeat sampling is budget-aware and concentrates on high-value, changed, or high-risk queries.
- Use `rtk` for repository commands and TDD for production changes.

---

### Task 1: Persist the governed query universe and repeated samples

**Files:**
- Create: `backend/app/models/tracked_query.py`
- Modify: `backend/app/models/scan_query_result.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py`
- Create: `backend/tests/test_tracked_query_model.py`
- Create: `backend/tests/test_measurement_migration.py`

**Produces:** `TrackedQuery`, repeated-sample metadata on `ScanQueryResult`, and the Phase 5 database migration.

- [ ] **Step 1: Write failing model and migration tests**

Assert that a tracked query belongs to one client, optionally one location, and has:

```python
text: str
normalized_text: str
source: str
intent: str
buyer_stage: str | None
service_key: str | None
risk_level: str
demand_weight: float
priority_score: float
is_active: bool
created_at: datetime
updated_at: datetime
```

Also assert that `ScanQueryResult` supports:

```python
tracked_query_id: UUID | None
sample_index: int
prompt_version: str
model_name: str
model_version: str | None
observed_at: datetime
```

Run:

```bash
cd backend
rtk pytest tests/test_tracked_query_model.py tests/test_measurement_migration.py -q
```

- [ ] **Step 2: Implement the models and migration**

Create revision `d1a7c5f4e0b2` with `down_revision = "c0f6b4e3d9a1"`.
Add foreign keys with explicit delete behavior, UTC timestamps, and check
constraints for positive `sample_index` and non-negative weights. Use two
partial unique indexes so brand-level queries cannot duplicate through a null
location:

```sql
CREATE UNIQUE INDEX uq_tracked_query_brand
ON tracked_queries (client_id, normalized_text)
WHERE location_id IS NULL;

CREATE UNIQUE INDEX uq_tracked_query_location
ON tracked_queries (client_id, location_id, normalized_text)
WHERE location_id IS NOT NULL;
```

Add indexes for:

```sql
(client_id, is_active, priority_score DESC)
(client_id, location_id, intent)
(tracked_query_id, observed_at DESC)
(scan_id, tracked_query_id, sample_index)
```

Enable RLS on `tracked_queries`, revoke `anon`, grant only the roles already used by SeenBy's authenticated backend pattern, and add explicit tenant policies matching the project migration convention. Do not expose `scan_query_results` directly to the browser.

- [ ] **Step 3: Verify upgrade and downgrade**

```bash
cd backend
rtk alembic upgrade head
rtk pytest tests/test_tracked_query_model.py tests/test_measurement_migration.py -q
rtk alembic downgrade c0f6b4e3d9a1
rtk alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
rtk git add backend/app/models/tracked_query.py backend/app/models/scan_query_result.py backend/app/models/__init__.py backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py backend/tests/test_tracked_query_model.py backend/tests/test_measurement_migration.py
rtk git commit -m "feat: add governed queries and repeated samples"
```

---

### Task 2: Build query governance and prioritization

**Files:**
- Create: `backend/app/schemas/tracked_query.py`
- Create: `backend/app/services/tracked_query_service.py`
- Create: `backend/app/api/v1/tracked_queries.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_tracked_query_service.py`
- Create: `backend/tests/test_api_tracked_queries.py`

**Produces:** Tenant-safe CRUD and deterministic priority calculation for the persistent query universe.

- [ ] **Step 1: Write failing service and API tests**

Cover normalization, duplicate prevention, cross-client denial, location ownership, archive instead of hard delete, and stable ordering. Test this scoring contract:

```python
priority = (
    demand_weight * 0.35
    + buyer_stage_weight * 0.20
    + risk_weight * 0.20
    + recent_change_weight * 0.15
    + business_value_weight * 0.10
)
```

The API accepts business inputs, never client-supplied computed weights.

- [ ] **Step 2: Implement schemas and service**

Use enums for `source`, `intent`, `buyer_stage`, and `risk_level`. Return both `priority_score` and a `priority_reasons: list[str]` calculated at read time. Normalize whitespace and Unicode before duplicate checks.

- [ ] **Step 3: Implement and register endpoints**

```text
GET    /clients/{client_id}/tracked-queries
POST   /clients/{client_id}/tracked-queries
PATCH  /clients/{client_id}/tracked-queries/{query_id}
POST   /clients/{client_id}/tracked-queries/{query_id}/archive
```

Require admin authentication and enforce client/location ownership in the service layer.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_tracked_query_service.py tests/test_api_tracked_queries.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/tracked_query.py backend/app/services/tracked_query_service.py backend/app/api/v1/tracked_queries.py backend/app/api/v1/router.py backend/tests/test_tracked_query_service.py backend/tests/test_api_tracked_queries.py
rtk git commit -m "feat: govern tracked query portfolio"
```

---

### Task 3: Add budget-aware repeat sampling

**Files:**
- Create: `backend/app/services/query_sampling_service.py`
- Modify: `backend/app/services/scan_service.py`
- Modify: `backend/app/services/budget_service.py`
- Create: `backend/tests/test_query_sampling_service.py`
- Modify: `backend/tests/test_api_scans.py`

**Produces:** A deterministic sampling plan and repeated observations tied to a tracked query.

- [ ] **Step 1: Write failing sampling tests**

Given a fixed budget, assert that the scheduler selects:

1. high-risk misinformation queries;
2. high-value queries with recent answer changes;
3. queries lacking the minimum sample count;
4. a rotating baseline sample;
5. no inactive query.

Assert deterministic selection for the same inputs and no duplicate `(tracked_query_id, model_name, sample_index)` within a scan.

- [ ] **Step 2: Implement the sampling contract**

```python
@dataclass(frozen=True)
class SamplingPlan:
    tracked_query_id: UUID
    repetitions: int
    reason_codes: tuple[str, ...]
    estimated_cost_usd: Decimal
```

Use three repetitions by default for high-priority queries and one for baseline queries. Let the existing budget service cap the final plan; do not bypass circuit breakers or cost logging.

- [ ] **Step 3: Integrate with scan execution**

Populate sample metadata in `ScanQueryResult`, retain the original query text for audit, and log model/prompt versions. A partial provider failure records only completed samples and leaves the scan recoverable.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_query_sampling_service.py tests/test_api_scans.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/services/query_sampling_service.py backend/app/services/scan_service.py backend/app/services/budget_service.py backend/tests/test_query_sampling_service.py backend/tests/test_api_scans.py
rtk git commit -m "feat: repeat high-value query sampling"
```

---

### Task 4: Calculate answer stability separately from visibility

**Files:**
- Create: `backend/app/schemas/query_stability.py`
- Create: `backend/app/services/query_stability_service.py`
- Create: `backend/tests/test_query_stability_service.py`

**Produces:** Per-query and portfolio stability with explicit sufficiency and volatility states.

- [ ] **Step 1: Write failing tests**

Cover:

```text
insufficient  fewer than 3 valid samples
emerging      present in one period, not yet repeated
repeated      consistent within one period
stable        consistent across at least 2 periods
volatile      material answer/citation/position disagreement
```

Test agreement for brand presence, recommendation status, normalized claim set, source-domain set, and position band. Missing provider output is `unobserved`, not a negative mention.

- [ ] **Step 2: Implement a versioned calculation**

Return:

```python
class QueryStability:
    state: Literal["insufficient", "emerging", "repeated", "stable", "volatile"]
    score: float | None
    sample_count: int
    period_count: int
    agreement: dict[str, float]
    calculation_version: str = "stability_v1"
```

Keep this independent from `GeoScore`; it may be displayed alongside the score but cannot overwrite it.

- [ ] **Step 3: Verify**

```bash
cd backend
rtk pytest tests/test_query_stability_service.py -q
```

- [ ] **Step 4: Commit**

```bash
rtk git add backend/app/schemas/query_stability.py backend/app/services/query_stability_service.py backend/tests/test_query_stability_service.py
rtk git commit -m "feat: calculate answer stability"
```

---

### Task 5: Normalize Search Console query evidence

**Files:**
- Create: `backend/app/models/search_query_signal.py`
- Create: `backend/app/schemas/search_query_signal.py`
- Create: `backend/app/services/search_console_service.py`
- Create: `backend/app/api/v1/search_console.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py`
- Create: `backend/tests/test_search_console_service.py`
- Create: `backend/tests/test_api_search_console.py`

**Produces:** Daily, normalized Search Console signals usable for evidence—not a raw Google data mirror.

- [ ] **Step 1: Verify the current Google Search Console API contract**

Before implementation, read Google's current official Search Analytics query documentation and OAuth data-retention guidance. Record the API version and selected dimensions in a code comment beside the adapter.

- [ ] **Step 2: Write failing adapter and ownership tests**

Test pagination, date windows, retries, duplicate upsert, property ownership, missing dimensions, and token redaction. Persist:

```python
client_id
location_id
property_uri
signal_date
query
page
country
device
clicks
impressions
ctr
position
synced_at
```

- [ ] **Step 3: Extend the Phase 5 migration**

Create `search_query_signals`, enable RLS, revoke anonymous access, and add:

```sql
UNIQUE (client_id, property_uri, signal_date, query, page, country, device)
INDEX  (client_id, signal_date DESC)
INDEX  (client_id, query, signal_date DESC)
```

- [ ] **Step 4: Implement sync and status endpoints**

```text
POST /clients/{client_id}/search-console/sync
GET  /clients/{client_id}/search-console/status
GET  /clients/{client_id}/search-console/signals
```

Store credentials through the existing secret/config mechanism only. Responses must not include access tokens, refresh tokens, or unbounded raw payloads.

- [ ] **Step 5: Verify**

```bash
cd backend
rtk pytest tests/test_search_console_service.py tests/test_api_search_console.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add backend/app/models/search_query_signal.py backend/app/schemas/search_query_signal.py backend/app/services/search_console_service.py backend/app/api/v1/search_console.py backend/app/api/v1/router.py backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py backend/tests/test_search_console_service.py backend/tests/test_api_search_console.py
rtk git commit -m "feat: normalize search console evidence"
```

---

### Task 6: Normalize conversion and revenue evidence

**Files:**
- Create: `backend/app/models/conversion_event.py`
- Create: `backend/app/schemas/conversion_event.py`
- Create: `backend/app/services/conversion_evidence_service.py`
- Create: `backend/app/api/v1/conversion_events.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py`
- Create: `backend/tests/test_conversion_evidence_service.py`
- Create: `backend/tests/test_api_conversion_events.py`

**Produces:** Deduplicated, evidence-labeled business events from GA4, CRM, call, booking, and manual sources.

- [ ] **Step 1: Write failing normalization tests**

Cover idempotent upsert by `(client_id, source, external_event_id)`, currency validation, location ownership, refunds/negative values, missing values, and these evidence levels:

```python
EvidenceLevel = Literal["observed", "attributed", "assisted", "estimated"]
```

An event cannot be upgraded to `observed` without a source record identifier and occurrence time.

- [ ] **Step 2: Extend the Phase 5 migration**

Create `conversion_events` with `event_type`, `occurred_at`, `value_minor`, `currency`, `evidence_level`, `source`, `external_event_id`, `source_url`, `metadata_json`, and calculation fields for estimated events. Add tenant/time and external-ID indexes, RLS, explicit policies, and anonymous revocation.

- [ ] **Step 3: Implement service and endpoints**

```text
POST /clients/{client_id}/conversion-events/import
GET  /clients/{client_id}/conversion-events
GET  /clients/{client_id}/conversion-events/summary
```

Allow raw event metadata only to authenticated admins. Apply an explicit field whitelist to client-view summaries.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_conversion_evidence_service.py tests/test_api_conversion_events.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/models/conversion_event.py backend/app/schemas/conversion_event.py backend/app/services/conversion_evidence_service.py backend/app/api/v1/conversion_events.py backend/app/api/v1/router.py backend/alembic/versions/d1a7c5f4e0b2_add_measurement_and_business_proof.py backend/tests/test_conversion_evidence_service.py backend/tests/test_api_conversion_events.py
rtk git commit -m "feat: normalize business outcome evidence"
```

---

### Task 7: Build the business-impact evidence ladder

**Files:**
- Create: `backend/app/schemas/business_impact.py`
- Create: `backend/app/services/business_impact_service.py`
- Create: `backend/app/api/v1/business_impact.py`
- Modify: `backend/app/api/v1/client_view.py`
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/tests/test_business_impact_service.py`
- Create: `backend/tests/test_api_business_impact.py`
- Modify: `backend/tests/test_api_client_view.py`

**Produces:** A versioned impact summary that cannot collapse estimated and observed outcomes into one number.

- [ ] **Step 1: Write failing calculation tests**

Require separate totals:

```python
class ImpactSummary:
    observed_value_minor: int
    attributed_value_minor: int
    assisted_value_minor: int
    estimated_value_minor: int
    currency: str
    event_count_by_level: dict[str, int]
    window_start: date
    window_end: date
    calculation_version: str
    caveats: list[str]
```

Mixed currencies must be separated or explicitly converted using a persisted rate and date. Never sum unknown currencies.

- [ ] **Step 2: Implement deterministic aggregation**

Join normalized conversion evidence to visibility/search signals only through documented, auditable rules. Return association confidence and reason codes; do not label a time-correlated event as caused by SeenBy.

- [ ] **Step 3: Add admin and client-safe APIs**

```text
GET /clients/{client_id}/business-impact
GET /view/{token}/business-impact
```

The public route omits external identifiers, raw metadata, internal confidence weights, and admin notes.

- [ ] **Step 4: Verify**

```bash
cd backend
rtk pytest tests/test_business_impact_service.py tests/test_api_business_impact.py tests/test_api_client_view.py -q
```

- [ ] **Step 5: Commit**

```bash
rtk git add backend/app/schemas/business_impact.py backend/app/services/business_impact_service.py backend/app/api/v1/business_impact.py backend/app/api/v1/client_view.py backend/app/schemas/client_view.py backend/app/api/v1/router.py backend/tests/test_business_impact_service.py backend/tests/test_api_business_impact.py backend/tests/test_api_client_view.py
rtk git commit -m "feat: expose defensible business impact"
```

---

### Task 8: Present stability and impact without false precision

**Files:**
- Create: `frontend/src/components/measurement/StabilityCard.tsx`
- Create: `frontend/src/components/measurement/EvidenceLadder.tsx`
- Create: `frontend/src/components/measurement/ImpactSummary.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/view-api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/app/(admin)/clients/[id]/page.tsx`
- Modify: `frontend/src/app/view/[token]/page.tsx`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/app/prompts/report.py`
- Create: `frontend/src/components/measurement/ImpactSummary.test.tsx`
- Modify: `backend/tests/test_api_report_generate.py`

**Produces:** Admin/client measurement views and reports with visible methodology and caveats.

- [ ] **Step 1: Write failing frontend and report tests**

Assert that:

- unavailable data displays “Not enough evidence,” not zero;
- estimated value is never visually merged with observed value;
- stability state includes sample and period counts;
- the report uses “associated with” for correlation and reserves “attributed” for configured attribution;
- every metric exposes its window and calculation version.

- [ ] **Step 2: Implement typed API clients and components**

Use the same Pydantic-to-TypeScript field names. Put observed evidence first, estimates last, and methodology in progressive disclosure.

- [ ] **Step 3: Integrate admin and client views**

Add measurement to the Phase 1 outcome navigation without restoring route sprawl. Preserve the strict public response whitelist.

- [ ] **Step 4: Update report generation**

Generate separate sections for visibility, stability, observed business evidence, attributed/assisted evidence, and scenarios. Do not let an LLM invent totals; pass all figures as deterministic structured inputs.

- [ ] **Step 5: Verify**

```bash
cd frontend
rtk npm test -- --run src/components/measurement/ImpactSummary.test.tsx
rtk npm run typecheck
cd ../backend
rtk pytest tests/test_api_report_generate.py -q
```

- [ ] **Step 6: Commit**

```bash
rtk git add frontend/src/components/measurement frontend/src/lib/api.ts frontend/src/lib/view-api.ts frontend/src/types/index.ts 'frontend/src/app/(admin)/clients/[id]/page.tsx' 'frontend/src/app/view/[token]/page.tsx' backend/app/services/report_service.py backend/app/prompts/report.py backend/tests/test_api_report_generate.py
rtk git commit -m "feat: present measurement evidence ladder"
```

---

### Task 9: Run the Phase 5 release gate

**Files:**
- Create: `docs/ops/measurement-runbook.md`
- Create: `docs/ops/release-checklist.md`

**Produces:** A verified, recoverable measurement release with explicit evidence semantics.

- [ ] **Step 1: Document operations**

Document sync ownership, sampling budgets, OAuth credential rotation, import idempotency, partial provider failures, backfill limits, calculation-version changes, and rollback to `c0f6b4e3d9a1`.

- [ ] **Step 2: Run backend verification**

```bash
cd backend
rtk alembic upgrade head
rtk pytest tests/test_tracked_query_model.py tests/test_measurement_migration.py tests/test_tracked_query_service.py tests/test_api_tracked_queries.py tests/test_query_sampling_service.py tests/test_query_stability_service.py tests/test_search_console_service.py tests/test_api_search_console.py tests/test_conversion_evidence_service.py tests/test_api_conversion_events.py tests/test_business_impact_service.py tests/test_api_business_impact.py tests/test_api_client_view.py tests/test_api_scans.py tests/test_api_report_generate.py -q
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

- [ ] **Step 4: Inspect RLS and query plans**

Using a non-owner test role, prove cross-tenant reads fail for every new table. Run `EXPLAIN (ANALYZE, BUFFERS)` for tracked-query priority, sample history, daily search signals, and conversion summaries; add indexes only from observed plans.

- [ ] **Step 5: Complete manual evidence checks**

For one client, show a tracked query moving from insufficient to repeated/stable or volatile, a duplicate import staying idempotent, an observed conversion remaining separate from an estimate, and client-view payloads containing no tokens, external IDs, or raw metadata.

- [ ] **Step 6: Commit**

```bash
rtk git add docs/ops/measurement-runbook.md docs/ops/release-checklist.md
rtk git commit -m "docs: add measurement release gate"
```
