# SeenBy Industry Intelligence Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Healthcare, F&B, and Local Services intelligence packs that specialize truth fields, buyer queries, risk routing, trusted sources, competitors, content recommendations, and reports without forking the horizontal platform.

**Architecture:** Define a typed pack protocol and registry. Store only the selected pack, subcategory, and pack version on Client; pack-specific business data remains in the shared Truth Vault. Query generation, risk rules, forms, and report language consume the registry through one interface.

**Tech Stack:** PostgreSQL, Alembic, SQLAlchemy, FastAPI, Pydantic, pytest, Next.js 15, React 19, TypeScript

## Global Constraints

- Requires Phases 0–3.
- Supported pack keys are `healthcare`, `fnb`, and `local_services`.
- A Client has exactly one primary pack in this release.
- Pack definitions are code-versioned and deterministic.
- Pack fields extend the shared Truth Vault; they do not create separate industry tables.
- Pack risk rules route evidence to human review and never declare professional or regulatory violations.
- Queries are generated from approved facts and locations only.
- Pack changes require an impact preview because query coverage and benchmarks change.
- Migration revision: `c0f6b4e3d9a1`, down revision: `b9e5a3d2c8f0`.
- Revoke anon access to any new table; this plan adds Client columns only.
- Use `rtk`, TDD, and focused commits.

---

### Task 1: Persist pack selection and version

**Files:**
- Modify: `backend/app/models/client.py`
- Modify: `backend/app/schemas/client.py`
- Create: `backend/alembic/versions/c0f6b4e3d9a1_add_industry_pack_to_clients.py`
- Create: `backend/tests/test_industry_pack_client.py`
- Modify: `backend/tests/test_api_clients.py`

**Interfaces:**
- Produces: `industry_pack`, `industry_subcategory`, and `industry_pack_version`.

- [ ] **Step 1: Write model and API tests**

Assert valid keys, nullable pre-migration clients, patching, prospect creation,
and rejection of unsupported keys. Test that changing pack returns an impact
preview flag before persistence.

- [ ] **Step 2: Add Client fields**

```python
industry_pack: Mapped[str | None] = mapped_column(String(32), nullable=True)
industry_subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
industry_pack_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

Validate keys in the service/API layer; use no PostgreSQL enum so adding a pack
does not require an enum migration.

- [ ] **Step 3: Backfill current industries**

The migration maps obvious values only:

```text
dental, clinic, hospital, medical -> healthcare
restaurant, cafe, food, catering -> fnb
```

Other clients remain null until admin review. Never guess local-services
subcategories from weak text.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_industry_pack_client.py tests/test_api_clients.py tests/test_migration_chain.py -v
rtk git add app/models/client.py app/schemas/client.py alembic/versions/c0f6b4e3d9a1_add_industry_pack_to_clients.py tests/test_industry_pack_client.py tests/test_api_clients.py
rtk git commit -m "feat: persist industry intelligence pack selection"
```

---

### Task 2: Define the typed pack protocol and registry

**Files:**
- Create: `backend/app/industry_packs/base.py`
- Create: `backend/app/industry_packs/registry.py`
- Create: `backend/app/industry_packs/__init__.py`
- Create: `backend/tests/test_industry_pack_registry.py`

**Interfaces:**
- Produces: `IndustryPack`, `TruthFieldDefinition`, `QueryTemplate`,
  `RiskRule`, `TrustedSourceType`, and `get_pack(key)`.

- [ ] **Step 1: Write registry tests**

Assert three keys, immutable versions, unique truth-field keys, unique risk
rule IDs, valid query intent/stage values, and unknown-key `KeyError`.

- [ ] **Step 2: Define immutable dataclasses**

```python
@dataclass(frozen=True)
class TruthFieldDefinition:
    key: str
    label: str
    value_type: Literal["text", "boolean", "number", "url", "list", "hours"]
    scope: Literal["brand", "location", "either"]
    risk_sensitive: bool = False
    required: bool = False

@dataclass(frozen=True)
class QueryTemplate:
    id: str
    template: str
    buyer_stage: Literal["awareness", "consideration", "decision"]
    commercial_intent: Literal["low", "medium", "high"]
    location_required: bool

@dataclass(frozen=True)
class IndustryPack:
    key: str
    version: str
    label: str
    subcategories: tuple[str, ...]
    truth_fields: tuple[TruthFieldDefinition, ...]
    query_templates: tuple[QueryTemplate, ...]
    risk_rules: tuple[RiskRule, ...]
    trusted_sources: tuple[TrustedSourceType, ...]
```

- [ ] **Step 3: Implement registry validation**

Validate on import and fail fast in development/tests. Return definitions by
reference because frozen dataclasses are immutable.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_industry_pack_registry.py -v
rtk git add app/industry_packs tests/test_industry_pack_registry.py
rtk git commit -m "feat: define intelligence pack contracts"
```

---

### Task 3: Implement the Healthcare pack

**Files:**
- Create: `backend/app/industry_packs/healthcare.py`
- Create: `backend/tests/test_healthcare_pack.py`
- Modify: `backend/app/industry_packs/registry.py`

**Interfaces:**
- Produces: `HEALTHCARE_PACK`, version `1.0.0`.

- [ ] **Step 1: Write pack contract tests**

Assert truth fields for practitioners, specialties, treatments, qualifications,
registrations, accreditations, facilities, and payment options. Assert
high-risk rules for credentials, invented treatments, practitioner-location
association, and unsupported outcomes.

- [ ] **Step 2: Define subcategories**

Include:

```python
("general_clinic", "dental", "specialist", "aesthetic",
 "physiotherapy", "diagnostics", "pharmacy", "other_healthcare")
```

- [ ] **Step 3: Define buyer queries**

Include brand, treatment discovery, practitioner, location, cost, eligibility,
comparison, and decision queries. Templates use only named placeholders:
`{brand}`, `{service}`, `{specialty}`, `{city}`, `{location}`.

- [ ] **Step 4: Define risk and source catalog**

Sources include official website, professional registry, accreditation body,
Google Business Profile, recognized directory, and reviewed publication.
Risk output says “needs review,” never “illegal” or “non-compliant.”

- [ ] **Step 5: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_healthcare_pack.py tests/test_industry_pack_registry.py -v
rtk git add app/industry_packs/healthcare.py app/industry_packs/registry.py tests/test_healthcare_pack.py
rtk git commit -m "feat: add healthcare intelligence pack"
```

---

### Task 4: Implement the F&B pack

**Files:**
- Create: `backend/app/industry_packs/fnb.py`
- Create: `backend/tests/test_fnb_pack.py`
- Modify: `backend/app/industry_packs/registry.py`

**Interfaces:**
- Produces: `FNB_PACK`, version `1.0.0`.

- [ ] **Step 1: Write pack contract tests**

Assert fields for outlets, menus, cuisine, dietary options, halal status and
source, price range, reservation, delivery, facilities, occasions, operating
hours, and kitchen hours.

- [ ] **Step 2: Define subcategories and queries**

Subcategories:

```python
("restaurant", "cafe", "bakery", "bar", "catering",
 "food_delivery", "quick_service", "other_fnb")
```

Queries cover dish/cuisine discovery, occasion, dietary requirement, location,
price/value, delivery, booking, and late-night availability.

- [ ] **Step 3: Define sensitive rules**

Halal claims require an approved fact and source. Dietary, allergen, menu,
price, outlet, and operating-hour conflicts route to review with severity
based on fact type.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_fnb_pack.py tests/test_industry_pack_registry.py -v
rtk git add app/industry_packs/fnb.py app/industry_packs/registry.py tests/test_fnb_pack.py
rtk git commit -m "feat: add food and beverage intelligence pack"
```

---

### Task 5: Implement the Local Services pack

**Files:**
- Create: `backend/app/industry_packs/local_services.py`
- Create: `backend/tests/test_local_services_pack.py`
- Modify: `backend/app/industry_packs/registry.py`

**Interfaces:**
- Produces: `LOCAL_SERVICES_PACK`, version `1.0.0`.

- [ ] **Step 1: Write pack contract tests**

Assert fields for service catalog, coverage area, availability, emergency or
same-day status, licensing, insurance, pricing model, warranties, response
time, exclusions, and booking channel.

- [ ] **Step 2: Define subcategories**

```python
("home_maintenance", "automotive", "beauty_wellness", "cleaning",
 "repair", "professional_local", "emergency_service",
 "other_local_service")
```

- [ ] **Step 3: Define queries and risk routing**

Queries cover problem/service, “near me,” emergency, same-day, coverage,
price, trust, warranty, and comparison. High-risk rules cover false licensing,
insurance, emergency availability, service area, and price guarantees.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_local_services_pack.py tests/test_industry_pack_registry.py -v
rtk git add app/industry_packs/local_services.py app/industry_packs/registry.py tests/test_local_services_pack.py
rtk git commit -m "feat: add local services intelligence pack"
```

---

### Task 6: Generate queries from pack definitions and approved facts

**Files:**
- Create: `backend/app/services/pack_query_service.py`
- Create: `backend/tests/test_pack_query_service.py`
- Modify: `backend/app/services/query_builder.py`
- Modify: `backend/tests/test_query_builder.py`
- Modify: `backend/app/services/scan_service.py`

**Interfaces:**
- Produces: `build_pack_queries(client, locations, facts, pack) -> list[BuiltQuery]`.

- [ ] **Step 1: Write query-generation tests**

Assert approved services and active locations only, stable dedupe, no blank
placeholder output, maximum configured query count, preserved control queries,
and no cross-location fact leakage.

- [ ] **Step 2: Implement placeholder expansion**

Allowed placeholders come from approved facts. A template with a missing
required placeholder is skipped and logged; never send braces or guessed
values to a model.

- [ ] **Step 3: Keep legacy fallback**

Clients without a reviewed pack continue using existing
`QUERY_TEMPLATES`. Packed clients use the registry. Preserve competitor and
control query behavior.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_pack_query_service.py tests/test_query_builder.py tests/test_scan_control_queries.py -v
rtk git add app/services/pack_query_service.py tests/test_pack_query_service.py app/services/query_builder.py tests/test_query_builder.py app/services/scan_service.py
rtk git commit -m "feat: build buyer queries from industry packs"
```

---

### Task 7: Apply pack-specific risk rules to Truth Vault conflicts

**Files:**
- Create: `backend/app/services/pack_risk_service.py`
- Create: `backend/tests/test_pack_risk_service.py`
- Modify: `backend/app/services/truth_comparison_service.py`
- Modify: `backend/app/services/misinformation_service.py`

**Interfaces:**
- Produces: `evaluate_pack_risk(pack, fact, conflict) -> PackRiskResult`.

- [ ] **Step 1: Write cross-pack risk tests**

The same opening-hour conflict is medium for a restaurant, while false
emergency availability is high for local services and false practitioner
credentials are critical for healthcare. All outputs remain needs-review.

- [ ] **Step 2: Implement rule matching**

Match by exact `fact_type`/`fact_key`, use the pack's configured severity and
review instruction, and fall back to medium. Return rule ID and pack version
for auditability.

- [ ] **Step 3: Persist rule provenance**

Store pack key/version/rule ID with the finding metadata. Do not overwrite a
human-adjusted severity on rescans.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_pack_risk_service.py tests/test_truth_comparison_service.py tests/test_misinformation_workflow.py -v
rtk git add app/services/pack_risk_service.py tests/test_pack_risk_service.py app/services/truth_comparison_service.py app/services/misinformation_service.py
rtk git commit -m "feat: route accuracy risk through industry packs"
```

---

### Task 8: Add pack selection and pack-driven Truth Vault forms

**Files:**
- Create: `frontend/src/lib/industry-packs.ts`
- Create: `frontend/src/lib/__tests__/industry-packs.test.ts`
- Modify: `frontend/src/app/(admin)/clients/[id]/settings/SettingsForm.tsx`
- Modify: `frontend/src/components/truth/FactEditor.tsx`
- Modify: `frontend/src/components/truth/LocationSelector.tsx`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Produces: frontend pack metadata that mirrors backend keys and field types.

- [ ] **Step 1: Write frontend catalog tests**

Assert exactly three pack keys, non-empty subcategories, unique field keys, and
supported input types.

- [ ] **Step 2: Implement selection with impact preview**

Before saving a pack change, show current query count, facts that remain
shared, pack-specific fields that become inactive, and benchmark reset.
Require confirmation.

- [ ] **Step 3: Render field definitions**

Use text, boolean, number, URL, list, and hours controls. Show source URL and
review requirement for risk-sensitive facts. Draft/approval lifecycle remains
unchanged.

- [ ] **Step 4: Verify and commit**

```powershell
cd frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk npm run build
rtk git add src/lib/industry-packs.ts src/lib/__tests__/industry-packs.test.ts 'src/app/(admin)/clients/[id]/settings/SettingsForm.tsx' src/components/truth/FactEditor.tsx src/components/truth/LocationSelector.tsx src/types/index.ts
rtk git commit -m "feat: configure industry intelligence packs"
```

---

### Task 9: Specialize content and report language

**Files:**
- Modify: `backend/app/prompts/content_analysis.py`
- Create: `backend/app/prompts/content_brief.py`
- Modify: `backend/app/prompts/content_roadmap.py`
- Modify: `backend/app/services/report_service.py`
- Create: `backend/tests/test_pack_prompt_context.py`
- Modify: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: pack definition plus approved facts.
- Produces: `build_pack_context(client, pack, facts) -> str`.

- [ ] **Step 1: Write prompt firewall tests**

Assert pack label, approved facts, risk instructions, and subcategory appear.
Assert drafts, reviewer notes, raw conflicts, internal IDs, and prohibited
professional-approval language do not.

- [ ] **Step 2: Add pack context to prompts**

Use one shared builder. Include “do not invent facts” and pack-sensitive claim
rules. Keep current language sanitizer and truncation handling.

- [ ] **Step 3: Add pack report labels**

Examples: “Practitioner facts reviewed,” “Outlet information reviewed,” and
“Service-area facts reviewed.” Use pack configuration; do not branch templates
through scattered `if industry` checks.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_pack_prompt_context.py tests/test_report_service.py tests/test_content_analysis_service.py tests/test_content_brief_service.py tests/test_content_roadmap_service.py -v
rtk git add app/prompts/content_analysis.py app/prompts/content_brief.py app/prompts/content_roadmap.py app/services/report_service.py tests/test_pack_prompt_context.py tests/test_report_service.py
rtk git commit -m "feat: specialize content and reports by industry pack"
```

---

### Task 10: Verify all three packs

- [ ] **Step 1: Verify the Phase 4 migration**

```powershell
cd backend
rtk alembic upgrade head
rtk alembic downgrade b9e5a3d2c8f0
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

- [ ] **Step 3: Complete one acceptance scenario per pack**

Create one Healthcare, one F&B, and one Local Services client. Confirm pack
selection, required brand facts, location facts, generated queries, risk
candidates, content brief, and report language for each.

- [ ] **Step 4: Verify pack-change safety**

Change one test client's pack and confirm the impact preview, audit entry,
legacy data preservation, explicit query regeneration, and benchmark reset.
Cancel a second change and confirm no state changed.

- [ ] **Step 5: Verify horizontal-core integrity**

Confirm no pack-specific table, forked API, or forked client portal exists.
Confirm no automatically generated output claims medical, professional,
regulatory, food-safety, licensing, or trade approval.

- [ ] **Step 6: Record the release evidence**

Attach the three conformance results, migration output, and pack-change audit
trace to the Phase 4 release checklist.
