# SeenBy Truth Vault and Location Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give SeenBy a versioned Business Truth Vault and one location hierarchy that supports both single-location businesses and private multi-location groups.

**Architecture:** Add brand-owned locations, stable fact identities, and append-only fact versions. Current Client fields remain operational during migration and are backfilled into approved truth facts. Accuracy services compare model statements with the fact version effective at observation time; client views receive only approved current facts and reviewed conflicts.

**Tech Stack:** PostgreSQL JSONB, Alembic, SQLAlchemy, FastAPI, Pydantic, pytest, Next.js 15, React 19, TypeScript

## Global Constraints

- Requires Phases 0–2.
- A single-location account is represented as one Client plus one primary location.
- Facts are append-only versions; updates create a new version.
- Historical scans compare against the fact version effective at scan time.
- Only approved facts may drive public content, client views, or confirmed accuracy findings.
- Draft facts and reviewer notes are administrator-only.
- Brand-wide facts use `location_id = NULL`; location facts use a client-owned location ID.
- Never delete a fact version referenced by evidence.
- Every new table receives RLS and anon grant revocation.
- Migration revision: `b9e5a3d2c8f0`, down revision: `b9e1f2a3c4d5`.
- Use `rtk`, TDD, reversible migrations, and focused commits.

---

### Task 1: Create locations and versioned truth tables

**Files:**
- Create: `backend/app/models/business_location.py`
- Create: `backend/app/models/truth_fact.py`
- Create: `backend/alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py`
- Create: `backend/tests/test_truth_models.py`
- Modify: `backend/app/models/outcome_action.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/test_outcome_action_model.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `BusinessLocation`, `TruthFact`, `TruthFactVersion`, and optional
  location scope for existing Outcome Actions.

- [ ] **Step 1: Write model round-trip and constraint tests**

Test one client with primary and secondary locations, one brand fact, one
location fact, two versions, effective periods, unique location slugs, and
client cascade. Assert an Outcome Action may reference a location owned by its
client and that deleting a location sets the action's `location_id` to null
without deleting the action.

- [ ] **Step 2: Define `BusinessLocation`**

Columns:

```text
id, client_id, name, slug, is_primary, website, address_line_1,
address_line_2, city, state, postcode, country, phone, latitude,
longitude, service_area_json, hours_json, booking_url, active,
created_at, updated_at
```

Unique `(client_id, slug)` and one partial unique primary location per client.

- [ ] **Step 3: Define fact identity and versions**

`TruthFact` columns:

```text
id, client_id, location_id, fact_type, fact_key, created_at
```

Use two explicit partial unique indexes so nullable location scope is
unambiguous:

```sql
CREATE UNIQUE INDEX uq_truth_fact_brand
ON truth_facts (client_id, fact_type, fact_key)
WHERE location_id IS NULL;

CREATE UNIQUE INDEX uq_truth_fact_location
ON truth_facts (client_id, location_id, fact_type, fact_key)
WHERE location_id IS NOT NULL;
```

`TruthFactVersion` columns:

```text
id, truth_fact_id, value_json, status, source_url, reviewer_note,
effective_from, effective_to, approved_at, approved_by, created_at
```

Statuses: `draft`, `approved`, `retired`. Only one open-ended approved version
per fact.

- [ ] **Step 4: Add location scope to Outcome Actions**

Add nullable `location_id` to `OutcomeAction`, backed by a foreign key to
`business_locations.id` with `ON DELETE SET NULL`. Add an index on
`(client_id, location_id, status)` for location queues. The migration creates
the location table before adding the foreign key and drops the foreign key
before dropping the table.

- [ ] **Step 5: Create migration, indexes, and RLS**

Create all tables and policies. Revoke anon access. Add indexes for client,
location, fact type, status, and effective-date lookup.

- [ ] **Step 6: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_truth_models.py tests/test_outcome_action_model.py tests/test_migration_chain.py -v
rtk git add app/models/business_location.py app/models/truth_fact.py app/models/outcome_action.py alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py tests/test_truth_models.py tests/test_outcome_action_model.py app/models/__init__.py tests/conftest.py
rtk git commit -m "feat: add truth vault and location persistence"
```

---

### Task 2: Implement location CRUD and ownership rules

**Files:**
- Create: `backend/app/schemas/business_location.py`
- Create: `backend/app/services/business_location_service.py`
- Create: `backend/app/api/v1/locations.py`
- Create: `backend/tests/test_business_location_service.py`
- Create: `backend/tests/test_api_locations.py`
- Modify: `backend/app/schemas/outcome_action.py`
- Modify: `backend/app/services/outcome_action_service.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/tests/test_outcome_action_service.py`

**Interfaces:**
- Produces: create/list/get/patch/deactivate location operations and
  tenant-checked location assignment for Outcome Actions.

- [ ] **Step 1: Write service and API tests**

Cover unique slugs, one primary location, cross-client `404`, active filtering,
primary reassignment, invalid latitude/longitude, and deactivation rather than
hard deletion. Also assert that assigning an Outcome Action to a location from
another client fails and that list filters accept only client-owned location
IDs.

- [ ] **Step 2: Define strict schemas**

Validate country as two-letter uppercase code, latitude `-90..90`, longitude
`-180..180`, and `hours_json` as seven day keys with closed/open periods.

- [ ] **Step 3: Implement service invariants**

When a new primary is set, clear the previous primary in the same transaction.
Reject deactivation of the only active location. Generate a slug from the name
and resolve collisions with `-2`, `-3`, and so on.

- [ ] **Step 4: Add routes**

```text
GET    /clients/{client_id}/locations
POST   /clients/{client_id}/locations
GET    /clients/{client_id}/locations/{location_id}
PATCH  /clients/{client_id}/locations/{location_id}
DELETE /clients/{client_id}/locations/{location_id}
```

DELETE performs deactivation.

- [ ] **Step 5: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_business_location_service.py tests/test_api_locations.py tests/test_outcome_action_service.py -v
rtk git add app/schemas/business_location.py app/services/business_location_service.py app/api/v1/locations.py app/schemas/outcome_action.py app/services/outcome_action_service.py tests/test_business_location_service.py tests/test_api_locations.py tests/test_outcome_action_service.py app/api/v1/router.py
rtk git commit -m "feat: manage client locations"
```

---

### Task 3: Implement append-only truth versioning

**Files:**
- Create: `backend/app/schemas/truth_fact.py`
- Create: `backend/app/services/truth_vault_service.py`
- Create: `backend/tests/test_truth_vault_service.py`

**Interfaces:**
- Produces: `create_fact`, `draft_version`, `approve_version`, `retire_fact`, `current_facts`, and `facts_effective_at`.

- [ ] **Step 1: Write versioning tests**

Assert approving a new version closes the old version one microsecond before
the new `effective_from`, historical lookup returns the old value, draft values
never appear in `current_facts`, and location ownership is enforced.

- [ ] **Step 2: Define schemas**

Use:

```python
class TruthValue(BaseModel):
    value: str | int | float | bool | list | dict | None
    display_value: str
```

Requests include `fact_type`, `fact_key`, optional location, value, source URL,
and effective date. Response includes version history for admins.

- [ ] **Step 3: Implement transaction-safe approval**

Lock the fact row with `FOR UPDATE`, validate no overlapping approved interval,
close the previous version, approve the draft, and commit once.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_truth_vault_service.py -v
rtk git add app/schemas/truth_fact.py app/services/truth_vault_service.py tests/test_truth_vault_service.py
rtk git commit -m "feat: version approved business facts"
```

---

### Task 4: Backfill current Client data without changing current APIs

**Files:**
- Create: `backend/app/services/truth_backfill_service.py`
- Create: `backend/tests/test_truth_backfill_service.py`
- Modify: `backend/alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py`

**Interfaces:**
- Produces: `backfill_client_truth(client_id, db) -> BackfillResult`.

- [ ] **Step 1: Write idempotent backfill tests**

Seed a Client with name, website, industry, phone, city, state, country, and
description. Run twice; assert one primary location, one fact identity per
field, and one approved version per identity.

- [ ] **Step 2: Implement mapping**

Map:

```python
CLIENT_FACT_MAP = {
    "official_name": "name",
    "website": "website",
    "industry": "industry",
    "description": "description",
    "phone": "phone",
}
```

Location fields map to the primary BusinessLocation. Skip null/blank values.
Use source URL `client-record://backfill` and reviewer `system:migration`.

- [ ] **Step 3: Add migration backfill**

Use SQL for the primary location and core facts so production upgrade is
self-contained. The Python service supports repair and tests after migration.
Do not remove Client columns.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_truth_backfill_service.py tests/test_migration_chain.py -v
rtk git add app/services/truth_backfill_service.py tests/test_truth_backfill_service.py alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py
rtk git commit -m "feat: backfill current clients into the truth vault"
```

---

### Task 5: Add Truth Vault admin APIs

**Files:**
- Create: `backend/app/api/v1/truth_vault.py`
- Create: `backend/tests/test_api_truth_vault.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Produces: admin fact list/create/version/approve/retire endpoints.

- [ ] **Step 1: Write API tests**

Cover auth, brand versus location scopes, current/history modes, drafts,
approval, retirement, URL validation, cross-client ownership, and pagination.

- [ ] **Step 2: Implement routes**

```text
GET   /clients/{client_id}/truth-facts
POST  /clients/{client_id}/truth-facts
GET   /clients/{client_id}/truth-facts/{fact_id}
POST  /clients/{client_id}/truth-facts/{fact_id}/versions
POST  /clients/{client_id}/truth-facts/{fact_id}/approve/{version_id}
POST  /clients/{client_id}/truth-facts/{fact_id}/retire
```

- [ ] **Step 3: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_api_truth_vault.py -v
rtk git add app/api/v1/truth_vault.py tests/test_api_truth_vault.py app/api/v1/router.py
rtk git commit -m "feat: expose truth vault administration"
```

---

### Task 6: Build Location and Truth Vault administration

**Files:**
- Create: `frontend/src/app/(admin)/clients/[id]/reputation/truth/page.tsx`
- Create: `frontend/src/app/(admin)/clients/[id]/reputation/truth/TruthVaultClient.tsx`
- Create: `frontend/src/app/(admin)/clients/[id]/reputation/truth/actions.ts`
- Create: `frontend/src/components/truth/FactEditor.tsx`
- Create: `frontend/src/components/truth/FactHistory.tsx`
- Create: `frontend/src/components/truth/LocationSelector.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/navigation.ts`

**Interfaces:**
- Consumes: Location and Truth Vault APIs.
- Produces: brand/location scoped fact editing and approval UI.

- [ ] **Step 1: Add exact frontend types and server actions**

Mirror backend status, scope, version, and date fields. Keep draft reviewer
notes out of public types.

- [ ] **Step 2: Build location selection and management**

Show Brand-wide plus active locations. Provide create/edit/deactivate flows and
require confirmation before primary-location reassignment.

- [ ] **Step 3: Build fact editing and history**

Group facts by Identity, Contact, Offering, Credentials, Policies, and Sources.
Editing creates a draft version. Approval is a separate button with source and
effective-date confirmation. History is read-only.

- [ ] **Step 4: Verify and commit**

```powershell
cd frontend
rtk npm run typecheck
rtk npm run build
rtk git add 'src/app/(admin)/clients/[id]/reputation/truth' src/components/truth src/lib/api.ts src/types/index.ts src/lib/navigation.ts
rtk git commit -m "feat: add truth vault administration"
```

---

### Task 7: Compare reviewed AI statements with effective facts

**Files:**
- Create: `backend/app/services/truth_comparison_service.py`
- Create: `backend/tests/test_truth_comparison_service.py`
- Modify: `backend/app/models/misinformation_finding.py`
- Modify: `backend/app/schemas/misinformation.py`
- Modify: `backend/app/services/misinformation_service.py`
- Modify: `backend/alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py`

**Interfaces:**
- Produces: `TruthConflictCandidate` and `compare_claims_to_truth(claims, facts)`.

- [ ] **Step 1: Add finding references**

Add nullable `truth_fact_id`, `truth_fact_version_id`, and `severity` to
misinformation findings in the Phase 3 migration and model.

- [ ] **Step 2: Write comparison tests**

Test exact match, normalized phone/hours match, list containment, conflicting
value, fact not effective at scan time, draft exclusion, and “needs review”
status.

- [ ] **Step 3: Implement typed comparators**

Use deterministic comparators for text, phone, URL, boolean, hours, and lists.
An LLM may extract a candidate statement, but it may not confirm the conflict.
Return supporting answer quote, approved value, source URL, and comparator.

- [ ] **Step 4: Integrate with misinformation review**

Store candidates as unconfirmed. A human reviewer confirms, rejects, or edits
severity. Never label a legal or professional violation automatically.

- [ ] **Step 5: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_truth_comparison_service.py tests/test_misinformation_workflow.py -v
rtk git add app/services/truth_comparison_service.py tests/test_truth_comparison_service.py app/models/misinformation_finding.py app/schemas/misinformation.py app/services/misinformation_service.py alembic/versions/b9e5a3d2c8f0_add_truth_vault_and_locations.py
rtk git commit -m "feat: compare AI claims with approved facts"
```

---

### Task 8: Expose approved location and truth summaries to clients

**Files:**
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/client_view.py`
- Create: `backend/tests/test_client_view_truth.py`
- Create: `frontend/src/app/view/[token]/reputation/page.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/view-api.ts`

**Interfaces:**
- Produces: strict-whitelist `ClientViewLocationSummary`,
  `ClientViewTruthHealth`, and reviewed conflict summaries.

- [ ] **Step 1: Write whitelist tests**

Assert approved current facts only. Exclude reviewer notes, draft values,
version IDs, approval tokens, internal severity reasoning, and source internals.

- [ ] **Step 2: Add public response**

Return location name, city, current hours summary, approved service categories,
fact freshness, reviewed open issue count, and corrected count.

- [ ] **Step 3: Render Reputation**

Show Accuracy Health, verified business information, location selector, open
reviewed issues, and resolved issues. Avoid a red alarm state for unreviewed
candidates.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_client_view_truth.py -v
cd ../frontend
rtk npm run typecheck
cd ..
rtk git add backend/app/schemas/client_view.py backend/app/api/v1/client_view.py backend/tests/test_client_view_truth.py 'frontend/src/app/view/[token]/reputation/page.tsx' frontend/src/types/index.ts frontend/src/lib/view-api.ts
rtk git commit -m "feat: show approved truth and accuracy health"
```

---

### Task 9: Verify Phase 3 migration, history, and privacy

- [ ] **Step 1: Upgrade, downgrade, and re-upgrade the migration**

```powershell
cd backend
rtk alembic upgrade head
rtk alembic downgrade b9e1f2a3c4d5
rtk alembic upgrade head
```

- [ ] **Step 2: Run automated verification**

```powershell
cd backend
rtk pytest -v
cd ../frontend
rtk npm test -- --run
rtk npm run typecheck
rtk npm run build
cd ..
rtk git diff --check
```

- [ ] **Step 3: Complete the truth-history acceptance scenario**

Create one brand fact and one location fact. Move each through draft, approval,
replacement, historical scan comparison, conflict review, and client display.
Confirm the older approved version remains queryable for its effective period.

- [ ] **Step 4: Prove tenant and public-view privacy**

Using a non-owner test role, verify cross-client reads fail for all three
tables. Confirm anonymous database access is revoked and client public APIs
never include drafts, reviewer notes, approval identities, or internal source
metadata.

- [ ] **Step 5: Record the release evidence**

Attach migration output, focused test output, one history trace, and one
redacted client response to the Phase 3 release checklist.
