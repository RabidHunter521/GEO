# SeenBy Delivery Operating System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect SeenBy evidence, recommendations, delivery, client approval, publication, verification, and proof through one Outcome Action lifecycle.

**Architecture:** Add `outcome_actions` as a unifying reference layer over existing recommendations, remediation items, briefs, deliverables, authority assets, and work-log entries. Existing specialist tables remain the source of domain details. Admin APIs manage the lifecycle; public clients receive strict-whitelist action summaries and expiring approval links.

**Tech Stack:** PostgreSQL, Alembic, SQLAlchemy, FastAPI, Pydantic, pytest, Next.js 15, React 19, TypeScript

## Global Constraints

- Requires Phase 0 and Phase 1.
- Preserve all specialist records; Outcome Actions reference rather than replace them.
- One source event creates at most one Outcome Action per client and source reference.
- Only reviewed, client-safe fields reach public schemas.
- Human approval is required before publication, truth changes, regulated claims, and final completion.
- Approval tokens are random, stored as SHA-256 hashes, expire, and are never logged.
- Status changes are validated server-side and recorded with timestamps.
- No action may claim a visibility change until a verification scan supports it.
- Every new table receives RLS and anon grant revocation in the same migration.
- Migration revision: `a8d4f2c1b7e9`, down revision: `d3f7a1c58e02`.
- Use `rtk`, TDD, and one commit per task.

---

### Task 1: Create the Outcome Action persistence model

**Files:**
- Create: `backend/app/models/outcome_action.py`
- Create: `backend/alembic/versions/a8d4f2c1b7e9_add_outcome_actions.py`
- Create: `backend/tests/test_outcome_action_model.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `OutcomeAction` and the status/type constants consumed by services.

- [ ] **Step 1: Write model round-trip tests**

Test required fields, nullable references, unique `(client_id, source_ref)`,
status defaults, timestamps, and client cascade. Use:

```python
action = OutcomeAction(
    client_id=client.id,
    action_type="content",
    title="Publish emergency plumbing page",
    rationale="High-intent query is currently won by two competitors.",
    priority="high",
    confidence="repeated",
    status="recommended",
    source_kind="content_gap",
    source_ref="content_gap:abc",
)
```

Assert default `created_at`, `updated_at`, and `status == "recommended"`.

- [ ] **Step 2: Define the SQLAlchemy model**

Include:

```python
OUTCOME_ACTION_TYPES = (
    "content", "technical", "structured_data", "fact_correction",
    "accuracy_review", "authority", "local_presence",
    "competitor_response", "measurement",
)
OUTCOME_ACTION_STATUSES = (
    "detected", "recommended", "approved_internal", "in_progress",
    "waiting_client", "ready_to_publish", "published",
    "waiting_verification", "verified", "no_change",
    "superseded", "dismissed",
)
```

Columns: IDs for client, optional scan, optional work log,
optional deliverable; source kind/ref; title; rationale; action type; priority;
`priority_score`; `priority_reasons` JSON; confidence; status; owner; due date;
destination URL; client-safe summary; `approval_token_hash`;
`approval_expires_at`; `client_decision`; `client_comment`;
`client_decided_at`; publication and verification timestamps; verification
result; created/updated timestamps. Add a unique index on non-null
`approval_token_hash` and never persist the plaintext token.

Location scope is intentionally added in Phase 3, after the shared
`business_locations` table exists. Phase 2 actions remain valid at brand/client
scope.

- [ ] **Step 3: Create the migration**

Create the table, foreign keys with `CASCADE` or `SET NULL`, a partial unique
index for non-null source refs, client/status and due-date indexes, RLS, and:

```sql
REVOKE ALL ON TABLE outcome_actions FROM anon;
```

Add a downgrade that drops policies, indexes, and the table.

- [ ] **Step 4: Verify model and migration chain**

```powershell
cd backend
rtk pytest tests/test_outcome_action_model.py tests/test_migration_chain.py -v
```

- [ ] **Step 5: Commit**

```powershell
rtk git add app/models/outcome_action.py alembic/versions/a8d4f2c1b7e9_add_outcome_actions.py tests/test_outcome_action_model.py app/models/__init__.py tests/conftest.py
rtk git commit -m "feat: add outcome action persistence"
```

---

### Task 2: Implement lifecycle validation and CRUD service

**Files:**
- Create: `backend/app/schemas/outcome_action.py`
- Create: `backend/app/services/outcome_action_service.py`
- Create: `backend/tests/test_outcome_action_service.py`

**Interfaces:**
- Produces: `create_action`, `list_actions`, `get_action`, `patch_action`, and `transition_action`.

- [ ] **Step 1: Write lifecycle tests**

Assert:

```python
transition_action(action, "in_progress", db)  # from approved_internal
```

passes, while:

```python
with pytest.raises(InvalidOutcomeTransition):
    transition_action(action, "verified", db)  # from recommended
```

fails. Test owner, due date, client-safe summary, destination URL, dismissal
reason, and client ownership filtering.

- [ ] **Step 2: Define request and response schemas**

Create `OutcomeActionCreate`, `OutcomeActionPatch`, `OutcomeActionOut`, and
`OutcomeActionListResponse`. Validate enum strings with `Literal`.

- [ ] **Step 3: Implement explicit transition graph**

```python
ALLOWED_TRANSITIONS = {
    "detected": {"recommended", "dismissed"},
    "recommended": {"approved_internal", "dismissed", "superseded"},
    "approved_internal": {"in_progress", "dismissed"},
    "in_progress": {"waiting_client", "ready_to_publish", "dismissed"},
    "waiting_client": {"in_progress", "ready_to_publish", "dismissed"},
    "ready_to_publish": {"published", "in_progress"},
    "published": {"waiting_verification"},
    "waiting_verification": {"verified", "no_change"},
    "no_change": {"waiting_verification", "superseded"},
}
```

Set `published_at` and `verified_at` only on their corresponding transitions.
Require `destination_url` for `published` and `verification_result` for
`verified`/`no_change`.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_outcome_action_service.py -v
rtk git add app/schemas/outcome_action.py app/services/outcome_action_service.py tests/test_outcome_action_service.py
rtk git commit -m "feat: enforce outcome action lifecycle"
```

---

### Task 3: Add idempotent adapters for existing SeenBy evidence

**Files:**
- Create: `backend/app/services/outcome_action_adapter_service.py`
- Create: `backend/tests/test_outcome_action_adapters.py`
- Modify: `backend/app/services/action_center_service.py`
- Modify: `backend/app/services/remediation_service.py`
- Modify: `backend/app/services/authority_service.py`
- Modify: `backend/app/services/deliverable_service.py`

**Interfaces:**
- Produces: `suggest_from_recommendation`, `suggest_from_remediation`, `suggest_from_authority`, and `link_deliverable`.

- [ ] **Step 1: Write adapter tests**

For each source, call the adapter twice and assert one Outcome Action. Assert
source refs:

```text
recommendation:{id}
remediation:{id}
authority:{id}
deliverable:{id}
```

Assert that linking a deliverable updates the existing action instead of
creating a second action.

- [ ] **Step 2: Implement one idempotent core**

```python
def suggest_once(
    *,
    client_id: uuid.UUID,
    source_kind: str,
    source_ref: str,
    action_type: str,
    title: str,
    rationale: str,
    priority: str,
    db: Session,
) -> OutcomeAction:
```

Query by client/source ref before insert; sanitize title and rationale; commit
only inside the caller's established transaction boundary.

- [ ] **Step 3: Call adapters after current source commits**

Keep hooks best-effort and never undo the source operation. Follow the current
work-log hook pattern with rollback and structured logging.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_outcome_action_adapters.py tests/test_work_log_hooks.py tests/test_authority_service.py tests/test_deliverable_service.py -v
rtk git add app/services/outcome_action_adapter_service.py tests/test_outcome_action_adapters.py app/services/action_center_service.py app/services/remediation_service.py app/services/authority_service.py app/services/deliverable_service.py
rtk git commit -m "feat: connect existing evidence to outcome actions"
```

---

### Task 4: Add explainable priority scoring

**Files:**
- Create: `backend/app/services/outcome_priority_service.py`
- Create: `backend/tests/test_outcome_priority_service.py`
- Modify: `backend/app/schemas/outcome_action.py`
- Modify: `backend/app/services/outcome_action_service.py`

**Interfaces:**
- Produces: `PriorityInputs`, `PriorityResult`, and `score_priority(inputs)`.

- [ ] **Step 1: Write the priority truth table**

Test deterministic weights:

```python
result = score_priority(PriorityInputs(
    commercial_intent=1.0,
    visibility_gap=1.0,
    competitor_advantage=0.8,
    reputation_risk=0.0,
    demand=0.6,
    expected_influence=0.7,
    confidence=0.8,
    effort=0.4,
))
assert result.band == "high"
assert "high commercial intent" in result.reasons
```

Clamp every input to `0..1`. Missing inputs use documented neutral defaults.

- [ ] **Step 2: Implement server-owned scoring**

Use:

```python
raw = (
    0.20 * commercial_intent
    + 0.15 * visibility_gap
    + 0.15 * competitor_advantage
    + 0.20 * reputation_risk
    + 0.10 * demand
    + 0.10 * expected_influence
    + 0.10 * confidence
) * (1.0 - 0.35 * effort)
```

Return a 0–100 score, `high >= 70`, `medium >= 40`, else `low`, plus at most
three plain-language reasons.

- [ ] **Step 3: Persist reasons**

Populate the `priority_score` and `priority_reasons` fields created by Task 1
whenever an action is created or its scoring inputs change. Store the
calculation version in the reasons payload so scores can be recomputed without
losing their lineage.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_outcome_priority_service.py tests/test_outcome_action_service.py -v
rtk git add app/services/outcome_priority_service.py tests/test_outcome_priority_service.py app/schemas/outcome_action.py app/services/outcome_action_service.py app/models/outcome_action.py alembic/versions
rtk git commit -m "feat: explain outcome action priority"
```

---

### Task 5: Expose authenticated action and review-queue APIs

**Files:**
- Create: `backend/app/api/v1/outcome_actions.py`
- Create: `backend/tests/test_api_outcome_actions.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/api/v1/work_log_global.py`

**Interfaces:**
- Produces: client-scoped list/create/patch/transition endpoints and global review queue.

- [ ] **Step 1: Write API tests**

Cover authentication, client ownership, status filters, due-date filters,
pagination, invalid transitions, and archived clients.

- [ ] **Step 2: Implement routes**

```text
GET    /clients/{client_id}/outcome-actions
POST   /clients/{client_id}/outcome-actions
GET    /clients/{client_id}/outcome-actions/{action_id}
PATCH  /clients/{client_id}/outcome-actions/{action_id}
POST   /clients/{client_id}/outcome-actions/{action_id}/transition
GET    /outcome-actions/review-queue
```

Return `404` for cross-client IDs. Limit page size to 100.

- [ ] **Step 3: Keep work-log queue compatible**

Do not delete `/work-log/review-queue`. The new Review Queue API returns
Outcome Actions, while existing work-log suggestions remain accessible until
their migration adapter reaches parity.

- [ ] **Step 4: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_api_outcome_actions.py tests/test_work_log_global.py -v
rtk git add app/api/v1/outcome_actions.py tests/test_api_outcome_actions.py app/api/v1/router.py app/api/v1/work_log_global.py
rtk git commit -m "feat: expose delivery action APIs"
```

---

### Task 6: Build the admin Delivery workspace

**Files:**
- Create: `frontend/src/app/(admin)/clients/[id]/delivery/page.tsx`
- Create: `frontend/src/app/(admin)/clients/[id]/delivery/DeliveryClient.tsx`
- Create: `frontend/src/app/(admin)/clients/[id]/delivery/actions.ts`
- Create: `frontend/src/components/delivery/ActionBoard.tsx`
- Create: `frontend/src/components/delivery/ActionDetailDialog.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/navigation.ts`
- Modify: `frontend/src/app/(admin)/review-queue/page.tsx`

**Interfaces:**
- Consumes: Outcome Action APIs.
- Produces: grouped action board and global operational queue.

- [ ] **Step 1: Add typed fetchers and server actions**

Mirror all response fields. Server actions call create, patch, and transition
endpoints and `revalidatePath`.

- [ ] **Step 2: Build lifecycle columns**

Columns: Recommended, In progress, Waiting for client, Ready to publish, and
Verification. Terminal actions appear in a separate completed filter.

- [ ] **Step 3: Build the action detail**

Show source evidence, rationale, priority reasons, owner, date, current status,
deliverable link, destination URL, and verification result. Render only valid
next transitions returned by a shared frontend transition map matching the
backend contract.

- [ ] **Step 4: Replace the global Review Queue data source**

Present accuracy review, client approval, publish-ready, verification-ready,
and overdue sections. Keep a link to legacy work-log suggestions while they
remain.

- [ ] **Step 5: Verify and commit**

```powershell
cd frontend
rtk npm run typecheck
rtk npm run build
rtk git add 'src/app/(admin)/clients/[id]/delivery' src/components/delivery src/lib/api.ts src/types/index.ts src/lib/navigation.ts 'src/app/(admin)/review-queue/page.tsx'
rtk git commit -m "feat: add the SeenBy delivery workspace"
```

---

### Task 7: Add expiring client approval links

**Files:**
- Create: `backend/app/services/action_approval_service.py`
- Create: `backend/app/schemas/action_approval.py`
- Create: `backend/app/api/v1/action_approvals.py`
- Create: `backend/tests/test_action_approval_service.py`
- Create: `backend/tests/test_api_action_approvals.py`
- Modify: `backend/app/models/outcome_action.py`
- Create: `frontend/src/app/view/action-approval/[token]/page.tsx`

**Interfaces:**
- Produces: `create_approval_link`, `resolve_approval_token`, and `record_client_decision`.

- [ ] **Step 1: Add token and decision fields**

Fields: `approval_token_hash`, `approval_expires_at`, `client_decision`,
`client_comment`, `client_decided_at`. These fields and the token-hash index
are created in Task 1; this task implements their service behavior and schemas.

- [ ] **Step 2: Write token security tests**

Assert 32-byte URL-safe tokens, SHA-256 storage, no plaintext persistence,
expiry, single-use decision, uniform `404` for invalid tokens, and a 2,000
character comment limit.

- [ ] **Step 3: Implement public whitelist endpoints**

```text
GET  /action-approvals/{token}
POST /action-approvals/{token}
```

GET returns business name, action title, client-safe summary, deliverable URL,
and expiry only. POST accepts `approve` or `request_changes` plus comment.

- [ ] **Step 4: Build the public approval page**

No client login. Set `robots: noindex, nofollow`; use server-side fetch; render
Approve and Request changes with confirmation. Never show source evidence,
priority internals, or admin notes.

- [ ] **Step 5: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_action_approval_service.py tests/test_api_action_approvals.py -v
cd ../frontend
rtk npm run typecheck
rtk npm run build
cd ..
rtk git add backend/app/services/action_approval_service.py backend/app/schemas/action_approval.py backend/app/api/v1/action_approvals.py backend/tests/test_action_approval_service.py backend/tests/test_api_action_approvals.py backend/app/models/outcome_action.py backend/alembic/versions 'frontend/src/app/view/action-approval/[token]/page.tsx'
rtk git commit -m "feat: add secure client action approvals"
```

---

### Task 8: Link publication, verification, and client proof

**Files:**
- Create: `backend/app/services/outcome_verification_service.py`
- Create: `backend/tests/test_outcome_verification_service.py`
- Modify: `backend/app/services/scan_service.py`
- Modify: `backend/app/services/work_log_service.py`
- Modify: `backend/app/schemas/client_view.py`
- Modify: `backend/app/api/v1/client_view.py`
- Modify: `frontend/src/app/view/[token]/content-plan/page.tsx`
- Modify: `frontend/src/app/view/[token]/progress/page.tsx`

**Interfaces:**
- Produces: `verify_waiting_actions(scan_id, client_id, db) -> VerificationSummary`.

- [ ] **Step 1: Write verification tests**

Test a published action tied to a query. A subsequent scan with repeated
brand presence transitions it to `verified`; absence transitions it to
`no_change`; missing comparable query leaves it waiting.

- [ ] **Step 2: Implement conservative verification**

Require source query identity and at least one post-publication scan. Store:

```json
{
  "basis": "query_presence",
  "before_seen": false,
  "after_seen": true,
  "scan_id": "...",
  "claim": "Observed after publication; causality not established"
}
```

Run best-effort after scan commit.

- [ ] **Step 3: Publish verified actions to the work log**

Create or update one client-safe WorkLogEntry using source ref
`outcome_action:{id}`. Only verified work is auto-suggested; an admin still
publishes it to clients.

- [ ] **Step 4: Expose client-safe actions**

Add whitelisted action-plan and completed-work schemas. The client sees title,
status label, due month, client-safe summary, destination URL, and verification
claim; never owner, internal rationale, priority formula, or source IDs.

- [ ] **Step 5: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_outcome_verification_service.py tests/test_client_view_work_log.py -v
cd ../frontend
rtk npm run typecheck
cd ..
rtk git add backend/app/services/outcome_verification_service.py backend/tests/test_outcome_verification_service.py backend/app/services/scan_service.py backend/app/services/work_log_service.py backend/app/schemas/client_view.py backend/app/api/v1/client_view.py 'frontend/src/app/view/[token]/content-plan/page.tsx' 'frontend/src/app/view/[token]/progress/page.tsx'
rtk git commit -m "feat: connect delivery actions to verified proof"
```

---

### Task 9: Verify the Delivery OS release gate

**Files:**
- Modify only for verified regressions.

- [ ] **Step 1: Run migrations against an empty test database**

Upgrade from base to head, downgrade one revision, and upgrade again. Run
`test_migration_chain.py`.

- [ ] **Step 2: Run all backend and frontend checks**

```powershell
cd backend
rtk pytest tests -q
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk npm run build
```

- [ ] **Step 3: Exercise one complete lifecycle**

Create evidence, approve internally, attach a deliverable, issue a client
approval link, approve, publish, run a comparable scan, verify, review the work
log, and publish client proof. Confirm every timestamp and status.

- [ ] **Step 4: Confirm backward compatibility**

Existing action recommendations, remediation, authority, content, work-log, and
public portal routes continue to work. No specialist record is deleted.
