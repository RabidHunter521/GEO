# SeenBy Trust and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SeenBy's current scoring, toolkit guidance, value language, activity presentation, and methodology claims accurate and internally consistent before the larger premium-platform redesign begins.

**Architecture:** Preserve the current database schema and API field names. Centralize product language in small backend and frontend modules, derive score-driving toolkit dimensions through one pure backend function, and cover each behavior with contract tests. This phase changes presentation and one score input rule; it does not add the Command Center, Outcome Action, Truth Vault, locations, intelligence packs, or new integrations.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Next.js 15, React 19, TypeScript, Vitest

## Global Constraints

- Preserve all existing client, scan, score, report, toolkit, work-log, and activity records.
- Keep current API field names such as `overall_score`, `technical_foundations_verified`, and `structured_data_verified`; this phase changes semantics and labels, not transport contracts.
- Use **Growth Readiness** as the user-facing name for the existing composite score.
- Use **AI Presence** only for observed mention and recommendation measurements; never use it as a synonym for Growth Readiness.
- Label revenue values as observed, attributed, assisted, or estimated. The current pipeline model is estimated.
- Treat `llms.txt` and `llms-full.txt` as optional publishing assets. Their presence must not independently increase Growth Readiness.
- Keep `robots.txt` AI-crawler access as the current Technical Foundations verification signal and schema markup as the current Structured Data verification signal.
- Bump `SCORE_VERSION` from `v1.3.0` to `v1.4.0` because the Technical Foundations formula changes.
- Do not delete or rewrite historical `GeoScore` rows. Newly computed rows use `v1.4.0`; historical rows retain their stored version.
- Human review remains required for misinformation, regulated claims, publishing, and final client reports.
- Prefix repository commands with `rtk` as required by `Claude.md`.
- Use TDD for production-code changes and commit after every independently reviewable task.
- Do not stage or modify `.claude/settings.local.json`.

---

## File responsibility map

### New files

- `backend/app/services/toolkit_dimension_service.py` — pure derivation of score-driving toolkit dimensions from crawler verification results.
- `backend/tests/test_toolkit_dimension_service.py` — truth table for toolkit-to-dimension semantics.
- `backend/tests/test_methodology_contract.py` — contract checks for score version, score labels, and methodology documentation.
- `frontend/src/lib/product-language.ts` — shared client-facing names for Growth Readiness and evidence levels.
- `frontend/src/lib/activity-presentation.ts` — exhaustive safe label and tone mapping for activity event types.
- `frontend/src/lib/__tests__/product-language.test.ts` — unit contracts for score and value language.
- `frontend/src/lib/__tests__/activity-presentation.test.ts` — unit contracts preventing raw event keys from appearing.
- `docs/methodology.md` — public-facing methodology, limitations, versioning, and evidence definitions.

### Existing files modified

- `backend/tests/test_work_log_hooks.py` — remove dependence on Windows clock resolution.
- `backend/app/api/v1/toolkit.py` — consume the pure toolkit dimension derivation.
- `backend/app/core/constants.py` — score version and canonical display label.
- `backend/tests/test_api_toolkit.py` — endpoint-level score semantics.
- `backend/tests/test_assessment_service.py` — version and display-label contract.
- `backend/app/services/site_audit_service.py` — neutral optional-file audit guidance.
- `backend/app/services/digest_tip_service.py` — remove unsupported visibility-gain claims.
- `backend/tests/test_site_audit_service.py` — site-audit copy contracts.
- `backend/tests/test_digest_tip.py` — digest copy contracts.
- `frontend/src/app/(admin)/clients/[id]/toolkit/ToolkitClient.tsx` — honest toolkit purpose and score-impact copy.
- `frontend/src/components/competitors/AIReadinessSection.tsx` — clarify informational competitor checks.
- `frontend/vitest.config.ts` — add a Node unit-test project alongside Storybook tests.
- `frontend/src/app/(admin)/clients/[id]/activity/page.tsx` — use safe event presentation and improved empty state.
- `frontend/src/app/(admin)/clients/[id]/page.tsx` — Growth Readiness label.
- `frontend/src/app/(admin)/clients/[id]/checklist/ChecklistClient.tsx` — Growth Readiness label.
- `frontend/src/app/(admin)/clients/[id]/ActionCenterCard.tsx` — Growth Readiness label.
- `frontend/src/app/(admin)/clients/[id]/reports/ReportsClient.tsx` — Growth Readiness label and scheduled empty state.
- `frontend/src/app/view/[token]/reports/page.tsx` — Growth Readiness label and delivery-cycle empty state.
- `frontend/src/app/view/[token]/progress/page.tsx` — active-delivery empty state.
- `frontend/src/components/view/AiPipelineValueCard.tsx` — explicit estimated methodology presentation.
- `backend/app/services/digest_service.py` — Growth Readiness label in digest subject and copy.
- `backend/app/services/alert_service.py` — Growth Readiness label in alerts.
- `backend/app/services/report_service.py` — Growth Readiness and estimated-impact report labels.
- `backend/tests/test_digest_service.py` — digest language contract.
- `backend/tests/test_alert_service.py` — alert language contract.
- `backend/tests/test_report_service.py` — report language contract.
- `Claude.md` — score-version note and formula definition.
- `FEATURES.md` — align implemented feature descriptions with the approved terminology.

## Phase 0 requirement traceability

| Approved Phase 0 requirement | Implemented by |
| --- | --- |
| Fix the order-dependent work-log test | Task 1 |
| Make optional publisher files non-score-driving | Tasks 2–3 |
| Version the changed Growth Readiness formula | Task 2 |
| Remove unsupported toolkit and site-audit claims | Task 3 |
| Separate Growth Readiness from AI Presence | Task 4 |
| Stop exposing raw activity event keys | Task 5 |
| Label estimated pipeline and won-business values | Task 6 |
| Improve empty Progress and Reports states | Task 6 |
| Publish methodology and resolve documentation drift | Task 7 |
| Identify internal test records without unsafe deletion | Task 8 |
| Verify backend, frontend, build, and prohibited copy | Task 8 |

---

### Task 1: Make the query-flip work-log test deterministic

**Files:**
- Modify: `backend/tests/test_work_log_hooks.py`

**Interfaces:**
- Consumes: `app.services.work_log_service.suggest_query_flips(client_id: UUID, db: Session) -> int`
- Produces: A deterministic regression test with an explicit previous and latest scan order.

- [ ] **Step 1: Reproduce the suite-order symptom**

Run from `backend`:

```powershell
rtk pytest tests/test_work_log_hooks.py::test_query_flips_write_visibility_suggestions -v
rtk pytest tests -q
```

Expected: the isolated test passes; the full suite currently reports
`assert 0 == 1` for the same test on affected Windows runs.

- [ ] **Step 2: Replace wall-clock timestamps with explicit ordered values**

Change the scan setup in `test_query_flips_write_visibility_suggestions`:

```python
from datetime import datetime

older = Scan(
    client_id=client.id,
    status="completed",
    completed_at=datetime(2026, 7, 1, 10, 0, 0),
)
newer = Scan(
    client_id=client.id,
    status="completed",
    completed_at=datetime(2026, 7, 8, 10, 0, 0),
)
db.add_all([older, newer])
db.commit()
```

Remove the local `utcnow` import. Keep the result rows and assertions unchanged.
The test's subject is query-flip behavior, not operating-system clock
resolution.

- [ ] **Step 3: Verify the focused test repeatedly**

Run from `backend`:

```powershell
1..20 | ForEach-Object {
  rtk pytest tests/test_work_log_hooks.py::test_query_flips_write_visibility_suggestions -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Expected: all 20 invocations pass.

- [ ] **Step 4: Verify the full backend suite**

Run from `backend`:

```powershell
rtk pytest tests -q
```

Expected: `926 passed` with no failure in
`test_query_flips_write_visibility_suggestions`.

- [ ] **Step 5: Commit**

```powershell
rtk git add tests/test_work_log_hooks.py
rtk git commit -m "test: stabilize query flip work-log coverage"
```

---

### Task 2: Decouple optional AI publishing files from score-driving dimensions

**Files:**
- Create: `backend/app/services/toolkit_dimension_service.py`
- Create: `backend/tests/test_toolkit_dimension_service.py`
- Modify: `backend/app/api/v1/toolkit.py`
- Modify: `backend/tests/test_api_toolkit.py`
- Modify: `backend/app/core/constants.py`
- Modify: `backend/tests/test_assessment_service.py`
- Modify: `Claude.md`

**Interfaces:**
- Consumes: crawler verification mapping with `llms_verified`, `llms_full_verified`, `robots_verified`, and `schema_verified`.
- Produces: `ToolkitDimensionState` and `derive_toolkit_dimensions(results: Mapping[str, bool]) -> ToolkitDimensionState`.
- Produces: `SCORE_VERSION == "v1.4.0"` and `SCORE_DISPLAY_LABEL == "Growth Readiness"`.

- [ ] **Step 1: Write the pure-function truth-table tests**

Create `backend/tests/test_toolkit_dimension_service.py`:

```python
from app.services.toolkit_dimension_service import derive_toolkit_dimensions


def test_robots_access_drives_technical_foundations():
    state = derive_toolkit_dimensions({
        "robots_verified": True,
        "schema_verified": False,
        "llms_verified": False,
        "llms_full_verified": False,
    })
    assert state.technical_foundations_verified is True
    assert state.structured_data_verified is False


def test_llms_files_do_not_drive_score_dimensions():
    state = derive_toolkit_dimensions({
        "robots_verified": False,
        "schema_verified": False,
        "llms_verified": True,
        "llms_full_verified": True,
    })
    assert state.technical_foundations_verified is False
    assert state.structured_data_verified is False


def test_schema_drives_structured_data_only():
    state = derive_toolkit_dimensions({
        "robots_verified": False,
        "schema_verified": True,
        "llms_verified": False,
        "llms_full_verified": False,
    })
    assert state.technical_foundations_verified is False
    assert state.structured_data_verified is True
```

- [ ] **Step 2: Run the new tests and verify the missing-module failure**

Run from `backend`:

```powershell
rtk pytest tests/test_toolkit_dimension_service.py -v
```

Expected: collection fails because
`app.services.toolkit_dimension_service` does not exist.

- [ ] **Step 3: Implement the pure derivation**

Create `backend/app/services/toolkit_dimension_service.py`:

```python
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ToolkitDimensionState:
    technical_foundations_verified: bool
    structured_data_verified: bool


def derive_toolkit_dimensions(
    results: Mapping[str, bool],
) -> ToolkitDimensionState:
    return ToolkitDimensionState(
        technical_foundations_verified=bool(results["robots_verified"]),
        structured_data_verified=bool(results["schema_verified"]),
    )
```

- [ ] **Step 4: Verify the pure-function tests**

Run from `backend`:

```powershell
rtk pytest tests/test_toolkit_dimension_service.py -v
```

Expected: three tests pass.

- [ ] **Step 5: Add endpoint-level failing assertions**

In `backend/tests/test_api_toolkit.py`, add:

```python
def test_verify_robots_without_llms_unlocks_technical_foundations():
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": False,
            "schema_verified": False,
            "robots_verified": True,
            "llms_full_verified": False,
        }
        response = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/toolkit/verify"
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.technical_foundations_verified is True
    assert fake_client.structured_data_verified is False


def test_verify_llms_without_robots_does_not_unlock_score():
    fake_client = _fake_client()
    fake_tf = _fake_toolkit(fake_client.id)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.first.return_value = fake_tf
    app.dependency_overrides[get_db] = lambda: mock_db
    with patch("app.api.v1.toolkit.verify_all") as mock_verify:
        mock_verify.return_value = {
            "llms_verified": True,
            "schema_verified": False,
            "robots_verified": False,
            "llms_full_verified": False,
        }
        response = TestClient(app).post(
            f"/api/v1/clients/{fake_client.id}/toolkit/verify"
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.technical_foundations_verified is False
```

- [ ] **Step 6: Run the endpoint tests and verify the old-formula failure**

Run from `backend`:

```powershell
rtk pytest tests/test_api_toolkit.py -v
```

Expected: the robots-without-llms assertion fails under the existing
`llms_verified and robots_verified` formula.

- [ ] **Step 7: Route the endpoint through the pure derivation**

In `backend/app/api/v1/toolkit.py`, import and use:

```python
from app.services.toolkit_dimension_service import derive_toolkit_dimensions

dimension_state = derive_toolkit_dimensions(results)
client.technical_foundations_verified = (
    dimension_state.technical_foundations_verified
)
client.structured_data_verified = dimension_state.structured_data_verified
```

Retain all four individual verification fields on `ToolkitFiles`. Change the
`verified_at` comment to state that it records a successful live check of a
core toolkit file (`llms.txt`, schema, or robots); it does not imply score
impact. Preserve the existing behavior where `llms-full.txt` alone does not
stamp `verified_at`.

- [ ] **Step 8: Bump and document the formula version**

In `backend/app/core/constants.py`:

```python
SCORE_VERSION: Final = "v1.4.0"
SCORE_DISPLAY_LABEL: Final = "Growth Readiness"
```

Update `test_assessment_constants_present`:

```python
assert constants.SCORE_VERSION == "v1.4.0"
assert constants.SCORE_DISPLAY_LABEL == "Growth Readiness"
```

Update `Claude.md` score-version text to:

```text
SCORE_VERSION = "v1.4.0" — Technical Foundations is driven by verified
robots.txt AI-crawler access; llms.txt and llms-full.txt are informational
publishing assets and do not drive the score.
```

- [ ] **Step 9: Verify score and toolkit tests**

Run from `backend`:

```powershell
rtk pytest tests/test_toolkit_dimension_service.py tests/test_api_toolkit.py tests/test_assessment_service.py tests/test_scoring_service.py -v
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit**

```powershell
rtk git add app/services/toolkit_dimension_service.py tests/test_toolkit_dimension_service.py app/api/v1/toolkit.py tests/test_api_toolkit.py app/core/constants.py tests/test_assessment_service.py ../Claude.md
rtk git commit -m "fix: make toolkit score semantics evidence-based"
```

---

### Task 3: Replace unsupported toolkit and site-audit claims

**Files:**
- Modify: `backend/app/services/site_audit_service.py`
- Modify: `backend/app/services/digest_tip_service.py`
- Modify: `backend/app/core/constants.py`
- Modify: `backend/tests/test_site_audit_service.py`
- Modify: `backend/tests/test_digest_tip.py`
- Modify: `frontend/src/app/(admin)/clients/[id]/toolkit/ToolkitClient.tsx`
- Modify: `frontend/src/components/competitors/AIReadinessSection.tsx`

**Interfaces:**
- Consumes: toolkit verification results and site-audit check dictionaries.
- Produces: neutral copy that distinguishes optional discovery files from verified crawl and schema signals.

- [ ] **Step 1: Write backend copy-contract tests**

Add to `backend/tests/test_site_audit_service.py`:

```python
def test_missing_llms_copy_is_optional_and_does_not_claim_visibility():
    routes = dict(_HEALTHY_ROUTES)
    routes["/llms.txt"] = SafeResponse(404)
    check = _by_id(_run(routes))["llms_txt"]
    combined = f"{check['detail']} {check['fix']}".lower()

    assert check["status"] == "warn"
    assert "optional" in combined
    assert "no summary" not in combined
    assert "visible" not in combined


def test_missing_llms_full_copy_does_not_claim_richer_ai_understanding():
    routes = dict(_HEALTHY_ROUTES)
    routes["/llms-full.txt"] = SafeResponse(404)
    check = _by_id(_run(routes))["llms_full_txt"]
    combined = f"{check['detail']} {check['fix']}".lower()

    assert check["status"] == "warn"
    assert "optional" in combined
    assert "richer picture" not in combined
```

Replace `test_rung2_toolkit_tip_when_no_battle_and_llms_unverified` in
`backend/tests/test_digest_tip.py` with:

```python
def test_rung2_technical_tip_does_not_promise_visibility_gain():
    client = make_client(technical_foundations_verified=False)
    tip = select_digest_tip(client, None, 55.0)

    assert "robots.txt" in tip
    assert "visibility gain" not in tip.lower()
    assert "llms.txt" not in tip
```

- [ ] **Step 2: Run the focused backend tests and verify failures**

Run from `backend`:

```powershell
rtk pytest tests/test_site_audit_service.py tests/test_digest_tip.py -v
```

Expected: the new copy assertions fail against the current claims.

- [ ] **Step 3: Implement neutral backend guidance**

In `backend/app/services/site_audit_service.py`, use:

```python
checks.append(_result(
    "llms_txt",
    "llms.txt file",
    "warn",
    "No llms.txt file found. This optional publisher-supplied summary is not "
    "required by major AI search platforms.",
    "Generate and publish llms.txt only if the client wants a maintained, "
    "machine-readable summary of its key pages.",
))
```

For missing `llms-full.txt`, use:

```python
checks.append(_result(
    "llms_full_txt",
    "llms-full.txt file",
    "warn",
    "No llms-full.txt file found. This optional extended publisher file is "
    "informational and does not affect Growth Readiness.",
    "Publish llms-full.txt only when the client can keep the extended content "
    "accurate and current.",
))
```

In `backend/app/services/digest_tip_service.py`, replace the old llms tip:

```python
if not client.technical_foundations_verified:
    return (
        "Review robots.txt this week so the AI search crawlers you choose to "
        "support are not accidentally blocked."
    )
```

In `backend/app/core/constants.py`, replace the developing static tip:

```python
"developing": (
    "Check that important service pages are crawlable, accurate, and linked "
    "clearly from your website."
),
```

- [ ] **Step 4: Correct the frontend Toolkit copy**

In `ToolkitClient.tsx`, replace the header description with:

```tsx
<p className="text-sm text-muted-foreground mt-1">
  Generate and verify optional publisher files, structured data, and crawler
  access. Only verified crawler access and structured data affect Growth
  Readiness.
</p>
```

Rename the verification panel:

```tsx
<p className="text-sm font-semibold">Growth Readiness impact</p>
```

Change the Technical Foundations result to:

```tsx
{verification.technical_foundations_updated ? (
  <span className="text-score-strong font-medium">
    &#10003; Verified &mdash; supported AI crawlers are allowed
  </span>
) : (
  <span className="text-muted-foreground">
    Review robots.txt AI-crawler access
  </span>
)}
```

Keep the `llms.txt` and `llms-full.txt` tabs. Add “Optional · no score impact”
to both tab descriptions. Do not remove generation, copying, downloading, or
live verification.

- [ ] **Step 5: Correct competitor readiness copy**

In `AIReadinessSection.tsx`, use:

```tsx
<p className="text-sm text-muted-foreground mt-1">
  Compares optional publisher files, AI-crawler access, and schema.org markup
  for your site and tracked competitors. This comparison is informational and
  does not change Growth Readiness.
</p>
```

- [ ] **Step 6: Verify backend tests and frontend types**

Run:

```powershell
cd backend
rtk pytest tests/test_site_audit_service.py tests/test_digest_tip.py -v
cd ../frontend
rtk npm run typecheck
```

Expected: backend tests pass and TypeScript reports no errors.

- [ ] **Step 7: Commit**

```powershell
rtk git add backend/app/services/site_audit_service.py backend/app/services/digest_tip_service.py backend/app/core/constants.py backend/tests/test_site_audit_service.py backend/tests/test_digest_tip.py 'frontend/src/app/(admin)/clients/[id]/toolkit/ToolkitClient.tsx' frontend/src/components/competitors/AIReadinessSection.tsx
rtk git commit -m "fix: make toolkit guidance evidence-based"
```

---

### Task 4: Centralize Growth Readiness and evidence language

**Files:**
- Create: `frontend/src/lib/product-language.ts`
- Create: `frontend/src/lib/__tests__/product-language.test.ts`
- Modify: `frontend/vitest.config.ts`
- Modify: `frontend/src/app/(admin)/clients/[id]/page.tsx`
- Modify: `frontend/src/app/(admin)/clients/[id]/checklist/ChecklistClient.tsx`
- Modify: `frontend/src/app/(admin)/clients/[id]/ActionCenterCard.tsx`
- Modify: `frontend/src/app/(admin)/clients/[id]/reports/ReportsClient.tsx`
- Modify: `frontend/src/app/view/[token]/reports/page.tsx`
- Modify: `backend/app/services/digest_service.py`
- Modify: `backend/app/services/alert_service.py`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/tests/test_digest_service.py`
- Modify: `backend/tests/test_alert_service.py`
- Modify: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: unchanged API properties such as `overall_score`.
- Produces: `PRODUCT_LANGUAGE`, `EvidenceLevel`, and `evidenceLabel(level)`.
- Produces: consistent Growth Readiness language in HTML, email, PDF, and web UI.

- [ ] **Step 1: Add a Node unit-test project**

In `frontend/vitest.config.ts`, keep the existing Storybook project and add:

```ts
{
  extends: true,
  test: {
    name: "unit",
    environment: "node",
    include: ["src/lib/__tests__/**/*.test.ts"],
  },
},
```

- [ ] **Step 2: Write failing product-language tests**

Create `frontend/src/lib/__tests__/product-language.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import {
  PRODUCT_LANGUAGE,
  evidenceLabel,
  type EvidenceLevel,
} from "../product-language"

describe("product language", () => {
  it("separates readiness from AI presence", () => {
    expect(PRODUCT_LANGUAGE.readiness).toBe("Growth Readiness")
    expect(PRODUCT_LANGUAGE.presence).toBe("AI Presence")
    expect(PRODUCT_LANGUAGE.readiness).not.toBe(PRODUCT_LANGUAGE.presence)
  })

  it.each([
    ["observed", "Observed"],
    ["attributed", "Attributed"],
    ["assisted", "Assisted"],
    ["estimated", "Estimated"],
  ] satisfies Array<[EvidenceLevel, string]>)(
    "labels %s evidence",
    (level, expected) => {
      expect(evidenceLabel(level)).toBe(expected)
    },
  )
})
```

- [ ] **Step 3: Run the unit test and verify the missing-module failure**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
```

Expected: the test fails because `product-language.ts` does not exist.

- [ ] **Step 4: Implement the frontend language contract**

Create `frontend/src/lib/product-language.ts`:

```ts
export const PRODUCT_LANGUAGE = {
  readiness: "Growth Readiness",
  presence: "AI Presence",
  accuracy: "Accuracy",
  businessImpact: "Business Impact",
} as const

export type EvidenceLevel =
  | "observed"
  | "attributed"
  | "assisted"
  | "estimated"

const EVIDENCE_LABELS: Record<EvidenceLevel, string> = {
  observed: "Observed",
  attributed: "Attributed",
  assisted: "Assisted",
  estimated: "Estimated",
}

export function evidenceLabel(level: EvidenceLevel): string {
  return EVIDENCE_LABELS[level]
}
```

- [ ] **Step 5: Verify the unit test**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
```

Expected: all unit tests pass.

- [ ] **Step 6: Replace frontend score labels without renaming API fields**

Import `PRODUCT_LANGUAGE` where the readiness score is presented and replace:

```tsx
Overall GEO Score
```

with:

```tsx
{PRODUCT_LANGUAGE.readiness}
```

Replace report table labels:

```tsx
<TableHead>{PRODUCT_LANGUAGE.readiness}</TableHead>
```

Replace checklist copy:

```tsx
label: `Confirm the baseline ${PRODUCT_LANGUAGE.readiness} across all 5 dimensions`,
```

Replace Action Center estimated-impact copy:

```tsx
Estimated readiness impact: +{action.estimated_impact} points
```

Do not change identifiers such as `overall_score`, `latest_overall_score`, or
`geo_score_id`.

- [ ] **Step 7: Write backend language-contract assertions**

In `test_build_report_html_contains_overall_score` in
`backend/tests/test_report_service.py`, retain the numeric assertion and add:

```python
assert "Growth Readiness" in html
assert "Overall GEO Score" not in html
```

In `test_build_report_html_contains_all_required_sections`, replace the old
composite-score section assertions with:

```python
assert "Growth Readiness" in html
assert "Readiness Breakdown" in html
assert "AI Visibility Score" not in html
```

In `test_subject_leads_with_seen_count_and_keeps_score` in
`backend/tests/test_digest_service.py`, add:

```python
assert "Growth Readiness" in subject
assert "GEO Score" not in subject
```

In the score-drop email test in `backend/tests/test_alert_service.py`, use its
existing `kwargs` mock-call dictionary:

```python
assert "Growth Readiness" in kwargs["subject"]
assert "GEO Score" not in kwargs["subject"]
assert "Growth Readiness" in kwargs["html_body"]
```

- [ ] **Step 8: Run backend tests and verify old labels fail**

Run from `backend`:

```powershell
rtk pytest tests/test_digest_service.py tests/test_alert_service.py tests/test_report_service.py -v
```

Expected: new Growth Readiness assertions fail while the services still emit
GEO Score copy.

- [ ] **Step 9: Use the canonical backend label**

Import:

```python
from app.core.constants import SCORE_DISPLAY_LABEL
```

Use `SCORE_DISPLAY_LABEL` in digest, alert, and report strings. For example:

```python
subject = f"{SCORE_DISPLAY_LABEL} update: {client.name}"
```

and:

```python
f"<div class=\"stat-label\">{SCORE_DISPLAY_LABEL}</div>"
```

Rename the report's `AI Visibility Score` heading to `Growth Readiness` and
`Score Breakdown` to `Readiness Breakdown`. Apply the canonical label to email
subjects, HTML bodies, Telegram text, and activity notes; these are all
administrator-visible surfaces.

Do not rename database columns, schema properties, or Python variables in this
phase.

- [ ] **Step 10: Verify the language surfaces**

Run:

```powershell
cd backend
rtk pytest tests/test_digest_service.py tests/test_alert_service.py tests/test_report_service.py -v
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
```

Expected: all selected backend tests, frontend unit tests, and TypeScript checks
pass.

- [ ] **Step 11: Commit**

```powershell
rtk git add frontend/vitest.config.ts frontend/src/lib/product-language.ts frontend/src/lib/__tests__/product-language.test.ts 'frontend/src/app/(admin)/clients/[id]/page.tsx' 'frontend/src/app/(admin)/clients/[id]/checklist/ChecklistClient.tsx' 'frontend/src/app/(admin)/clients/[id]/ActionCenterCard.tsx' 'frontend/src/app/(admin)/clients/[id]/reports/ReportsClient.tsx' 'frontend/src/app/view/[token]/reports/page.tsx' backend/app/services/digest_service.py backend/app/services/alert_service.py backend/app/services/report_service.py backend/tests/test_digest_service.py backend/tests/test_alert_service.py backend/tests/test_report_service.py
rtk git commit -m "refactor: separate readiness from AI presence"
```

---

### Task 5: Prevent raw activity event keys from reaching the interface

**Files:**
- Create: `frontend/src/lib/activity-presentation.ts`
- Create: `frontend/src/lib/__tests__/activity-presentation.test.ts`
- Modify: `frontend/src/app/(admin)/clients/[id]/activity/page.tsx`

**Interfaces:**
- Consumes: `ActivityLogEntry.event_type: string`.
- Produces: `presentActivityType(eventType: string) -> ActivityPresentation`.

- [ ] **Step 1: Write failing activity-presentation tests**

Create `frontend/src/lib/__tests__/activity-presentation.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { presentActivityType } from "../activity-presentation"

describe("presentActivityType", () => {
  it.each([
    ["authority_assets_added", "Authority opportunities added"],
    ["brief_generated", "Content brief prepared"],
    ["traffic_updated", "AI traffic data updated"],
    ["toolkit_verified", "Technical files checked"],
  ])("maps %s to client-safe copy", (eventType, expected) => {
    const result = presentActivityType(eventType)
    expect(result.label).toBe(expected)
    expect(result.label).not.toContain("_")
  })

  it("humanizes unknown keys instead of exposing raw enums", () => {
    const result = presentActivityType("future_event_key")
    expect(result.label).toBe("Future event key")
    expect(result.label).not.toContain("_")
  })
})
```

- [ ] **Step 2: Run the unit tests and verify the missing-module failure**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
```

Expected: the new test fails because `activity-presentation.ts` does not exist.

- [ ] **Step 3: Implement safe activity presentation**

Create `frontend/src/lib/activity-presentation.ts`:

```ts
export type ActivityTone =
  | "success"
  | "warning"
  | "danger"
  | "information"
  | "neutral"

export interface ActivityPresentation {
  label: string
  tone: ActivityTone
}

const ACTIVITY_PRESENTATION: Record<string, ActivityPresentation> = {
  scan_completed: { label: "Visibility scan completed", tone: "success" },
  scan_failed: { label: "Visibility scan needs attention", tone: "danger" },
  toolkit_generated: { label: "Technical files prepared", tone: "information" },
  toolkit_verified: { label: "Technical files checked", tone: "success" },
  client_created: { label: "Client onboarded", tone: "neutral" },
  digest_sent: { label: "Weekly update sent", tone: "information" },
  report_generated: { label: "Monthly report prepared", tone: "information" },
  report_sent: { label: "Monthly report delivered", tone: "success" },
  alert_sent: { label: "Visibility alert sent", tone: "warning" },
  hallucination_flagged: { label: "Potential accuracy issue found", tone: "warning" },
  content_analyzed: { label: "Content opportunities analyzed", tone: "information" },
  authority_assets_added: { label: "Authority opportunities added", tone: "information" },
  authority_status_changed: { label: "Authority work updated", tone: "information" },
  brief_generated: { label: "Content brief prepared", tone: "information" },
  deliverable_generated: { label: "Content deliverable prepared", tone: "information" },
  traffic_updated: { label: "AI traffic data updated", tone: "information" },
  page_audit_run: { label: "Page citability checked", tone: "information" },
  site_audit_run: { label: "Website readiness checked", tone: "information" },
  citation_flip: { label: "Citation source changed", tone: "information" },
}

function humanize(eventType: string): string {
  const words = eventType.replaceAll("_", " ").trim()
  if (!words) return "Activity updated"
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function presentActivityType(eventType: string): ActivityPresentation {
  return ACTIVITY_PRESENTATION[eventType] ?? {
    label: humanize(eventType),
    tone: "neutral",
  }
}
```

- [ ] **Step 4: Verify the unit tests**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
```

Expected: all product-language and activity-presentation tests pass.

- [ ] **Step 5: Consume the presenter in the Activity page**

Remove the local `EVENT_LABELS`. Import:

```tsx
import { presentActivityType } from "@/lib/activity-presentation"
```

Change the implicit-return row map to a block body:

```tsx
{entries.map((entry) => {
  const presentation = presentActivityType(entry.event_type)
  return (
    <div
      key={entry.id}
      className="flex items-start gap-3 px-4 py-3 transition-colors hover:bg-muted/30"
    >
      <EventIcon type={entry.event_type} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium leading-none">
          {presentation.label}
        </p>
        <p className="text-sm text-muted-foreground mt-1">{entry.note}</p>
      </div>
      <p className="text-xs text-muted-foreground shrink-0 mt-0.5 tabular-nums">
        {formatDate(entry.created_at)}
      </p>
    </div>
  )
})}
```

Keep `EventIcon` keyed by the persisted event type. Change the warning label
from “Hallucination flagged” to the presenter's
“Potential accuracy issue found.”

- [ ] **Step 6: Improve the admin empty state**

Use:

```tsx
<p className="font-medium">The activity timeline will start with the first scan</p>
<p className="text-sm mt-1">
  Scans, reviewed findings, delivered work, reports, and verification events
  will appear here.
</p>
```

Keep the existing link to Scan & Visibility.

- [ ] **Step 7: Verify frontend contracts**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
rtk npm run typecheck
```

Expected: all unit tests and TypeScript checks pass.

- [ ] **Step 8: Commit**

```powershell
rtk git add frontend/src/lib/activity-presentation.ts frontend/src/lib/__tests__/activity-presentation.test.ts 'frontend/src/app/(admin)/clients/[id]/activity/page.tsx'
rtk git commit -m "fix: present activity events in human language"
```

---

### Task 6: Make pipeline value and empty delivery states explicit

**Files:**
- Modify: `frontend/src/lib/product-language.ts`
- Modify: `frontend/src/lib/__tests__/product-language.test.ts`
- Modify: `frontend/src/components/view/AiPipelineValueCard.tsx`
- Modify: `frontend/src/app/view/[token]/progress/page.tsx`
- Modify: `frontend/src/app/view/[token]/reports/page.tsx`
- Modify: `frontend/src/app/(admin)/clients/[id]/reports/ReportsClient.tsx`
- Modify: `backend/app/services/report_service.py`
- Modify: `backend/tests/test_report_service.py`

**Interfaces:**
- Consumes: `ClientViewTrafficValue` with `ai_visitors`, `est_leads`, `est_pipeline_rm`, `est_won_rm`, and `breakdown_label`.
- Produces: `formatEvidenceStatement(level, value, noun) -> string`.
- Produces: empty states that describe the next delivery milestone.

- [ ] **Step 1: Extend the failing product-language tests**

Extend the existing import from `../product-language` to include
`formatEvidenceStatement`, then add:

```ts
it("makes estimated values explicit", () => {
  expect(formatEvidenceStatement("estimated", "RM 16,000", "pipeline"))
    .toBe("Estimated pipeline: RM 16,000")
})

it("makes observed values explicit", () => {
  expect(formatEvidenceStatement("observed", "84", "AI referral visits"))
    .toBe("Observed AI referral visits: 84")
})
```

- [ ] **Step 2: Run the unit test and verify the missing-function failure**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
```

Expected: `formatEvidenceStatement` is missing.

- [ ] **Step 3: Implement the evidence formatter**

Add to `product-language.ts`:

```ts
export function formatEvidenceStatement(
  level: EvidenceLevel,
  value: string,
  noun: string,
): string {
  return `${evidenceLabel(level)} ${noun}: ${value}`
}
```

- [ ] **Step 4: Update the pipeline card hierarchy**

In `AiPipelineValueCard.tsx`:

```tsx
<h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
  Estimated AI Pipeline
</h2>
```

Use separate lines:

```tsx
<p className="mt-3 font-display text-3xl font-bold tabular-nums text-foreground">
  {rm(value.est_pipeline_rm as number)}
</p>
<p className="mt-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
  Estimated from configured conversion assumptions
</p>
<p className="mt-3 text-sm text-muted-foreground">
  Observed AI referral visitors:{" "}
  <span className="font-semibold text-foreground">
    {value.ai_visitors.toLocaleString("en-MY")}
  </span>
</p>
```

Retain estimated leads and estimated won business, but prefix both with
“Estimated.” Do not describe estimated won business as confirmed revenue.

- [ ] **Step 5: Add a report-copy failing assertion**

In `test_build_report_html_renders_pipeline_rm_when_configured` in
`backend/tests/test_report_service.py`, add:

```python
assert "Estimated from configured conversion assumptions" in html
assert "Confirmed revenue" not in html
```

- [ ] **Step 6: Run the report test and verify the copy failure**

Run from `backend`:

```powershell
rtk pytest tests/test_report_service.py -v
```

Expected: the methodology phrase is absent.

- [ ] **Step 7: Update report impact labels**

In `backend/app/services/report_service.py`, label current modelled values:

```python
<div class="impact-method">
  Estimated from configured conversion assumptions
</div>
```

Use “Observed AI referral visits,” “Estimated leads,” “Estimated pipeline,” and
“Estimated won business.” Do not add a new attribution calculation in this
phase.

- [ ] **Step 8: Improve client and admin delivery empty states**

Client Progress:

```tsx
<p className="mt-4 font-display text-lg font-semibold">
  Your first delivery cycle is being prepared
</p>
<p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
  Reviewed actions will appear here after the SeenBy team completes and
  publishes them.
</p>
```

Client Reports:

```tsx
<p className="mt-4 font-display text-lg font-semibold">
  Your first monthly report is scheduled
</p>
<p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
  It will appear here after the first reporting period has been reviewed and
  delivered.
</p>
```

Admin Reports:

```tsx
<p className="font-medium">No reviewed report has been delivered yet</p>
<p className="text-sm mt-1">
  Generate the first report, review its evidence and estimates, then send it
  to the client.
</p>
```

- [ ] **Step 9: Verify the selected surfaces**

Run:

```powershell
cd backend
rtk pytest tests/test_report_service.py -v
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
```

Expected: all selected tests and TypeScript checks pass.

- [ ] **Step 10: Commit**

```powershell
rtk git add frontend/src/lib/product-language.ts frontend/src/lib/__tests__/product-language.test.ts frontend/src/components/view/AiPipelineValueCard.tsx 'frontend/src/app/view/[token]/progress/page.tsx' 'frontend/src/app/view/[token]/reports/page.tsx' 'frontend/src/app/(admin)/clients/[id]/reports/ReportsClient.tsx' backend/app/services/report_service.py backend/tests/test_report_service.py
rtk git commit -m "fix: label estimated business impact clearly"
```

---

### Task 7: Publish methodology and align feature documentation

**Files:**
- Create: `docs/methodology.md`
- Create: `backend/tests/test_methodology_contract.py`
- Modify: `FEATURES.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: `SCORE_VERSION`, `SCORE_DISPLAY_LABEL`, four measurement layers, and current scan behavior.
- Produces: one canonical methodology document and executable documentation contracts.

- [ ] **Step 1: Write the failing documentation contract**

Create `backend/tests/test_methodology_contract.py`:

```python
from pathlib import Path

from app.core.constants import SCORE_DISPLAY_LABEL, SCORE_VERSION


ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "methodology.md"


def test_methodology_documents_current_score_contract():
    text = METHODOLOGY.read_text(encoding="utf-8")
    assert SCORE_VERSION in text
    assert SCORE_DISPLAY_LABEL in text
    assert "AI Presence" in text
    assert "Accuracy and Reputation" in text
    assert "Business Impact" in text


def test_methodology_discloses_optional_files_and_uncertainty():
    text = METHODOLOGY.read_text(encoding="utf-8").lower()
    assert "llms.txt" in text
    assert "optional" in text
    assert "does not independently increase" in text
    assert "answers can vary" in text
    assert "estimated" in text
```

- [ ] **Step 2: Run the contract and verify the missing-file failure**

Run from `backend`:

```powershell
rtk pytest tests/test_methodology_contract.py -v
```

Expected: failure because `docs/methodology.md` does not exist.

- [ ] **Step 3: Create the methodology document**

Create `docs/methodology.md` with these exact top-level sections:

```markdown
# SeenBy Measurement Methodology

## Measurement layers

### AI Presence
Observed mentions, recommendations, platform coverage, and competitor
share-of-voice across the tracked buyer-query set.

### Accuracy and Reputation
Potential conflicts between model answers and approved business facts. Findings
remain needs-review until a human confirms them.

### Growth Readiness
The current composite leading indicator. Version v1.4.0 combines AI citability,
brand authority, content quality, verified robots.txt AI-crawler access, and
verified structured data.

### Business Impact
Observed traffic and intent events are separated from attributed, assisted, and
estimated leads or revenue.

## Query coverage

Describe tracked platforms, client-specific query templates, competitor
queries, control queries, locations, and the fact that the configured universe
is a monitored sample rather than every real user question.

## Sampling and variability

State that generated answers can vary between runs, platforms, model versions,
locations, and sessions. A single observed change is evidence, not proof of a
durable market shift.

## Technical and publisher files

State that robots.txt controls crawler access, structured data describes page
entities, and llms.txt plus llms-full.txt are optional publisher-supplied
formats. Their presence does not independently increase Growth Readiness or
guarantee AI visibility.

## Attribution and estimates

Define observed, attributed, assisted, and estimated. Document the current
visitor-to-lead, deal-value, and close-rate assumptions and state that estimated
pipeline is not confirmed revenue.

## Versioning

Document v1.4.0 and state that historical score rows retain their original
score version.

## Limitations

State platform coverage, API-versus-consumer-experience limits, sampling
variability, incomplete referral identification, and the boundary between
factual review routing and professional compliance advice.
```

Write each section as finished prose. Keep terminology identical to
`2026-07-29-seenby-premium-platform-design.md`.

- [ ] **Step 4: Verify the methodology contract**

Run from `backend`:

```powershell
rtk pytest tests/test_methodology_contract.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Align feature and architecture documents**

In `FEATURES.md` and `docs/architecture.md`:

- Replace current user-facing “GEO Score” descriptions with “Growth Readiness
  (`overall_score` in the current API).”
- Describe `llms.txt` and `llms-full.txt` as optional.
- State that Technical Foundations currently reflects verified `robots.txt`
  AI-crawler access.
- Link to `docs/methodology.md`.
- Mark already shipped provenance, causality, GA4, misinformation, authority,
  page-citability, reports, and review-queue capabilities as implemented where
  the code and current UI confirm them.

- [ ] **Step 6: Run documentation and code checks**

Run:

```powershell
cd backend
rtk pytest tests/test_methodology_contract.py tests/test_assessment_service.py -v
cd ..
rtk grep "make your client visible to AI search engines|quickest visibility gain|AI assistants have no summary" backend frontend FEATURES.md docs
```

Expected: methodology tests pass and the prohibited claim search returns no
matches.

- [ ] **Step 7: Commit**

```powershell
rtk git add docs/methodology.md backend/tests/test_methodology_contract.py FEATURES.md docs/architecture.md
rtk git commit -m "docs: publish SeenBy measurement methodology"
```

---

### Task 8: Phase 0 verification and operational data-hygiene review

**Files:**
- Modify only if verification exposes a Phase 0 regression.
- Do not modify or delete production client data in this task.

**Interfaces:**
- Consumes: all outputs from Tasks 1–7.
- Produces: verification evidence and an exact list of suspected internal test accounts for owner review.

- [ ] **Step 1: Run the full backend suite**

Run from `backend`:

```powershell
rtk pytest tests -q
```

Expected: all backend tests pass, including the deterministic query-flip test
and methodology contracts.

- [ ] **Step 2: Run frontend unit tests and type checking**

Run from `frontend`:

```powershell
rtk npx vitest run --project unit
rtk npm run typecheck
```

Expected: all unit tests pass and TypeScript reports no errors.

- [ ] **Step 3: Build the frontend**

Stop any running Next.js development server first, then run from `frontend`:

```powershell
rtk npm run build
```

Expected: Next.js completes a production build successfully.

- [ ] **Step 4: Run prohibited-language and raw-enum scans**

Run from the repository root:

```powershell
rtk grep "make your client visible to AI search engines|quickest visibility gain|AI assistants have no summary|Overall GEO Score" backend frontend
rtk grep "authority_assets_added|brief_generated|traffic_updated" frontend/src/app
```

Expected: the first command returns no user-facing prohibited claims; the
second finds no raw event-key rendering in route components. Persisted backend
event names and the centralized presentation map are allowed.

- [ ] **Step 5: Review suspected internal test accounts without deleting data**

Use the existing admin client list and prospect list to record the exact client
names and IDs that are clearly internal test data. Produce a review note in the
execution log with:

```text
client_id | client_name | current_status | evidence_it_is_internal | proposed_action
```

Do not archive or delete any account until the owner confirms the exact rows.
Prospects are a supported acquisition workflow and must not be hidden merely
because they are prospects.

- [ ] **Step 6: Confirm staged scope**

Run from the repository root:

```powershell
rtk git status --short
rtk git diff --check
rtk git log --oneline -8
```

Expected: only intentional Phase 0 changes are present; no generated
environment, cache, credential, or local-settings files are staged.

- [ ] **Step 7: Record final verification**

Add the exact command outputs and pass counts to the implementation-session
handoff. If a verification command fails, report the failing command and
failure count; do not describe Phase 0 as complete.
