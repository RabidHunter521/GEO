# SeenBy Premium Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize SeenBy's existing capabilities into outcome-led admin and client experiences without moving or deleting the underlying routes, records, or services.

**Architecture:** Add a read-only Command Center aggregation service over existing score, scan, remediation, work-log, traffic, report, and action data. Group the current admin routes in navigation, compress the public client portal into six outcome destinations, and put raw query and competitor evidence behind deterministic summaries and drill-downs.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Next.js 15, React 19, TypeScript, Vitest

## Global Constraints

- Requires the Phase 0 Trust and Reliability plan to be complete.
- Preserve current routes during this phase; navigation labels and grouping may change.
- Preserve strict client-view schema whitelists. Never reuse admin response schemas in `/api/v1/view/{token}`.
- Keep client links read-only and non-indexable.
- Use Growth Readiness, AI Presence, Accuracy, and Business Impact as distinct concepts.
- Put summaries before raw evidence; do not remove evidence.
- Hide or contextualize empty client modules rather than implying completed delivery.
- Keep administration desktop-first and make client consumption work at 360px width.
- Add no new database tables in this phase.
- Use `rtk` for repository commands and TDD for production changes.

---

### Task 1: Build the admin Command Center aggregation contract

**Files:**
- Create: `backend/app/schemas/command_center.py`
- Create: `backend/app/services/command_center_service.py`
- Create: `backend/tests/test_command_center_service.py`
- Modify: `backend/app/api/v1/clients.py`
- Modify: `backend/tests/test_api_clients.py`

**Interfaces:**
- Consumes: existing `GeoScore`, `Scan`, `RemediationItem`, `WorkLogEntry`, `ActionRecommendation`, `AiTrafficSnapshot`, and `Report` rows.
- Produces: `build_command_center(client: Client, db: Session) -> CommandCenterResponse`.
- Produces: `GET /api/v1/clients/{client_id}/command-center`.

- [ ] **Step 1: Write the aggregation tests**

Create `backend/tests/test_command_center_service.py` with fixtures that seed one
client, two scores, one open action, one flagged remediation item, one published
work-log entry, and one traffic snapshot. Assert:

```python
result = build_command_center(client, db)
assert result.metrics.ai_presence.value == 45.0
assert result.metrics.growth_readiness.value == 60.0
assert result.attention.accuracy_risks == 1
assert result.delivery.completed_last_30d == 1
assert result.priority_actions[0].action_text == "Publish the service page"
assert result.period_story.headline == "AI Presence improved by 15.0 points"
```

Add a no-data test:

```python
result = build_command_center(client, db)
assert result.metrics.ai_presence.value is None
assert result.period_story.headline == "Baseline measurement is being prepared"
assert result.priority_actions == []
```

- [ ] **Step 2: Verify the missing-service failure**

Run from `backend`:

```powershell
rtk pytest tests/test_command_center_service.py -v
```

Expected: import failure for `command_center_service`.

- [ ] **Step 3: Define focused response schemas**

In `backend/app/schemas/command_center.py`, define:

```python
class MetricValue(BaseModel):
    value: float | None
    delta: float | None = None
    evidence_label: str

class CommandCenterMetrics(BaseModel):
    ai_presence: MetricValue
    accuracy: MetricValue
    growth_readiness: MetricValue
    business_impact: MetricValue

class PeriodStory(BaseModel):
    headline: str
    bullets: list[str] = []

class AttentionSummary(BaseModel):
    accuracy_risks: int
    overdue_actions: int
    stale_scan: bool

class DeliverySummary(BaseModel):
    in_progress: int
    waiting_for_client: int
    ready_to_publish: int
    completed_last_30d: int

class CommandCenterAction(BaseModel):
    id: uuid.UUID
    action_text: str
    priority: str
    reason: str

class CommandCenterResponse(BaseModel):
    metrics: CommandCenterMetrics
    period_story: PeriodStory
    attention: AttentionSummary
    delivery: DeliverySummary
    priority_actions: list[CommandCenterAction]
```

Accuracy is `100 - confirmed_open_risk_percentage`; until the Phase 3 Truth
Vault exists, use confirmed open misinformation/remediation counts and return
`None` when there is no reviewed accuracy evidence. Business Impact uses
observed AI visitors and is labelled `Observed`.

- [ ] **Step 4: Implement deterministic aggregation**

Create `command_center_service.py`. Query the two newest scores ordered by
`computed_at DESC, id DESC`; calculate AI Presence and Growth Readiness deltas;
count reviewed risks and published work; and select at most five open actions.
Build narrative text only from stored values:

```python
def _change_headline(current: float | None, previous: float | None) -> str:
    if current is None:
        return "Baseline measurement is being prepared"
    if previous is None:
        return f"AI Presence baseline established at {current:.1f}%"
    delta = round(current - previous, 1)
    if delta > 0:
        return f"AI Presence improved by {delta:.1f} points"
    if delta < 0:
        return f"AI Presence declined by {abs(delta):.1f} points"
    return "AI Presence held steady"
```

Do not call an LLM from this service.

- [ ] **Step 5: Add the authenticated endpoint**

Add to `backend/app/api/v1/clients.py`:

```python
@router.get("/{client_id}/command-center", response_model=CommandCenterResponse)
def command_center(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    return build_command_center(client, db)
```

Add API tests for `200`, archived-client `404`, and response schema.

- [ ] **Step 6: Verify and commit**

```powershell
cd backend
rtk pytest tests/test_command_center_service.py tests/test_api_clients.py -v
rtk git add app/schemas/command_center.py app/services/command_center_service.py tests/test_command_center_service.py app/api/v1/clients.py tests/test_api_clients.py
rtk git commit -m "feat: add client command center aggregation"
```

---

### Task 2: Group the admin navigation without breaking routes

**Files:**
- Create: `frontend/src/lib/navigation.ts`
- Create: `frontend/src/lib/__tests__/navigation.test.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Produces: `ADMIN_GLOBAL_NAV`, `CLIENT_NAV_GROUPS`, and `isNavItemActive(pathname, clientId, href)`.

- [ ] **Step 1: Write the navigation contract**

Create `navigation.test.ts` asserting the five client groups and legacy hrefs:

```ts
expect(CLIENT_NAV_GROUPS.map((group) => group.label)).toEqual([
  "Intelligence", "Reputation", "Growth", "Delivery", "Proof", "Setup",
])
expect(CLIENT_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href)))
  .toContain("/content-roadmap")
expect(isNavItemActive("/clients/abc/scan", "abc", "/scan")).toBe(true)
```

- [ ] **Step 2: Run the failing unit test**

```powershell
cd frontend
rtk npx vitest run --project unit
```

Expected: `navigation.ts` is missing.

- [ ] **Step 3: Implement the route-preserving map**

Create `navigation.ts` with:

```ts
export const CLIENT_NAV_GROUPS = [
  { label: "Intelligence", items: [
    { href: "/scan", label: "AI Presence" },
    { href: "/competitors", label: "Competitors" },
  ]},
  { label: "Reputation", items: [
    { href: "/toolkit", label: "Technical Foundations" },
    { href: "/authority", label: "Authority" },
  ]},
  { label: "Growth", items: [
    { href: "/content-gaps", label: "Opportunities" },
    { href: "/content-roadmap", label: "Content Plan" },
    { href: "/content-studio", label: "Content Production" },
  ]},
  { label: "Delivery", items: [
    { href: "/checklist", label: "Action Plan" },
    { href: "/activity", label: "Delivery & Progress" },
  ]},
  { label: "Proof", items: [
    { href: "/reports", label: "Reports" },
  ]},
  { label: "Setup", items: [
    { href: "/settings", label: "Client Setup" },
  ]},
] as const
```

Keep Overview as an ungrouped first item. Add the existing Lucide icon
references in `Sidebar.tsx`, because component values do not belong in the
serializable navigation module.

- [ ] **Step 4: Render grouped sections**

Refactor `Sidebar.tsx` to map `CLIENT_NAV_GROUPS`, print group headings, and use
the existing active-bar styling. Keep All Clients, Portfolio Intelligence
(existing Gap Matrix), and Review Queue globally accessible.

- [ ] **Step 5: Verify and commit**

```powershell
cd frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk git add src/lib/navigation.ts src/lib/__tests__/navigation.test.ts src/components/layout/Sidebar.tsx
rtk git commit -m "refactor: group SeenBy navigation by outcome"
```

---

### Task 3: Replace the admin Overview with the Command Center

**Files:**
- Create: `frontend/src/components/command-center/OutcomeMetricCard.tsx`
- Create: `frontend/src/components/command-center/PeriodStoryCard.tsx`
- Create: `frontend/src/components/command-center/PriorityActionsCard.tsx`
- Create: `frontend/src/components/command-center/DeliveryStatusCard.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/app/(admin)/clients/[id]/page.tsx`

**Interfaces:**
- Consumes: `GET /clients/{id}/command-center`.
- Produces: `getCommandCenter(clientId): Promise<CommandCenter>`.

- [ ] **Step 1: Add the frontend response type and fetcher**

Mirror the backend schema exactly in `types/index.ts`; implement:

```ts
export async function getCommandCenter(clientId: string): Promise<CommandCenter> {
  return apiFetch(`/api/v1/clients/${clientId}/command-center`)
}
```

- [ ] **Step 2: Build four focused components**

Each component receives typed data and no client ID except where links are
required. `OutcomeMetricCard` renders label, value, delta, and evidence label.
`PriorityActionsCard` links each row to its existing destination based on
dimension. `DeliveryStatusCard` renders counts and never invents completed work.

- [ ] **Step 3: Compose the page**

Replace the current score-first hierarchy with:

```tsx
<OutcomeMetrics metrics={data.metrics} />
<PeriodStoryCard story={data.period_story} />
<div className="grid gap-6 xl:grid-cols-2">
  <PriorityActionsCard actions={data.priority_actions} clientId={id} />
  <DeliveryStatusCard summary={data.delivery} clientId={id} />
</div>
```

Retain useful current trend, benchmark, site-audit, and guarantee components
below the new command layer. Do not delete them.

- [ ] **Step 4: Verify responsive layout**

```powershell
cd frontend
rtk npm run typecheck
rtk npm run build
```

Use the approved Playwright workflow at 1440x900 and 390x844. Verify no clipped
cards, horizontal overflow, or hidden primary links.

- [ ] **Step 5: Commit**

```powershell
rtk git add src/components/command-center src/lib/api.ts src/types/index.ts 'src/app/(admin)/clients/[id]/page.tsx'
rtk git commit -m "feat: make the command center the admin overview"
```

---

### Task 4: Add a deterministic client-period summary

**Files:**
- Modify: `backend/app/schemas/client_view.py`
- Create: `backend/app/services/client_period_summary_service.py`
- Create: `backend/tests/test_client_period_summary_service.py`
- Modify: `backend/app/api/v1/client_view.py`
- Modify: `backend/tests/test_api_client_view.py`
- Create: `frontend/src/components/view/PeriodSummary.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/app/view/[token]/page.tsx`

**Interfaces:**
- Produces: `ClientViewPeriodSummary` with `headline`, `wins`, `risks`, `work_underway`, and `next_actions`.
- Produces: `build_client_period_summary(client, db) -> ClientViewPeriodSummary`.

- [ ] **Step 1: Write backend summary tests**

Seed two scores, proof cards, one reviewed risk, one open action, and one
published work item. Assert every returned sentence contains stored evidence
and no raw response text or internal event key.

- [ ] **Step 2: Implement the schema and pure narrative builder**

```python
class ClientViewPeriodSummary(BaseModel):
    headline: str
    wins: list[str] = []
    risks: list[str] = []
    work_underway: list[str] = []
    next_actions: list[str] = []
```

Cap each list at three items. Use deterministic templates only. Add
`period_summary: ClientViewPeriodSummary` to `ClientViewOverview`.

- [ ] **Step 3: Verify whitelist behavior**

```powershell
cd backend
rtk pytest tests/test_client_period_summary_service.py tests/test_api_client_view.py -v
```

- [ ] **Step 4: Render the summary first**

Create `PeriodSummary.tsx` and place it immediately after the public overview
hero. Move detailed proof cards, charts, dimensions, and remediation sections
below it. Use “View evidence” anchor links to the detailed sections.

- [ ] **Step 5: Verify and commit**

```powershell
cd frontend
rtk npm run typecheck
cd ..
rtk git add backend/app/schemas/client_view.py backend/app/services/client_period_summary_service.py backend/tests/test_client_period_summary_service.py backend/app/api/v1/client_view.py backend/tests/test_api_client_view.py frontend/src/components/view/PeriodSummary.tsx frontend/src/types/index.ts 'frontend/src/app/view/[token]/page.tsx'
rtk git commit -m "feat: summarize the client reporting period"
```

---

### Task 5: Simplify client navigation and add a mobile section selector

**Files:**
- Modify: `frontend/src/components/view/ViewTabs.tsx`
- Modify: `frontend/src/app/view/[token]/layout.tsx`
- Create: `frontend/src/app/view/[token]/reputation/page.tsx`
- Modify: `frontend/src/lib/view-api.ts`

**Interfaces:**
- Consumes: current overview capability flags.
- Produces: Overview, Visibility, Reputation, Action Plan, Progress, and Reports.

- [ ] **Step 1: Define the six destinations**

Use the existing routes:

```ts
[
  { segment: "", label: "Overview" },
  { segment: "/scan", label: "Visibility" },
  { segment: "/reputation", label: "Reputation" },
  { segment: "/content-plan", label: "Action Plan" },
  { segment: "/progress", label: "Progress" },
  { segment: "/reports", label: "Reports" },
]
```

Keep competitor evidence linked from Visibility and Overview rather than as a
primary tab. Preserve the `/competitors` route for existing links.

- [ ] **Step 2: Build the Reputation page from whitelisted APIs**

Fetch `/issues` and `/progress`; show reviewed accuracy issues, corrected
items, and authority/technical summaries only when data exists. Do not expose
admin activity notes.

- [ ] **Step 3: Replace clipped mobile tabs**

At `sm` and above, keep tabs. Below `sm`, render a labelled `<select>` whose
change handler calls `router.push`. Ensure the selected option follows
`usePathname()`.

- [ ] **Step 4: Verify accessibility and mobile behavior**

Run typecheck and build. At 390x844 verify the selector label, focus outline,
44px touch height, current-page value, and no horizontal navigation clipping.

- [ ] **Step 5: Commit**

```powershell
rtk git add frontend/src/components/view/ViewTabs.tsx 'frontend/src/app/view/[token]/layout.tsx' 'frontend/src/app/view/[token]/reputation/page.tsx' frontend/src/lib/view-api.ts
rtk git commit -m "refactor: simplify the client portal navigation"
```

---

### Task 6: Add progressive disclosure to scan and competitor evidence

**Files:**
- Create: `frontend/src/lib/query-segments.ts`
- Create: `frontend/src/lib/__tests__/query-segments.test.ts`
- Modify: `frontend/src/app/view/[token]/scan/page.tsx`
- Modify: `frontend/src/app/view/[token]/competitors/page.tsx`
- Modify: `frontend/src/app/(admin)/clients/[id]/scan/ScanClient.tsx`

**Interfaces:**
- Produces: `segmentQueries(results) -> QuerySegments`.

- [ ] **Step 1: Write query segmentation tests**

Assert stable segmentation into newly seen, newly lost, high-intent unseen, and
other evidence. Ensure each result appears in exactly one segment.

- [ ] **Step 2: Implement the pure segmenter**

```ts
export interface QuerySegments<T> {
  newlySeen: T[]
  newlyLost: T[]
  opportunities: T[]
  other: T[]
}
```

Use explicit fields supplied by the page; do not infer commercial intent from
free text in this phase.

- [ ] **Step 3: Render summaries before tables**

Show segment counts and the first five rows per segment. Add “Show all N”
buttons and platform/category filters. Keep all existing evidence accessible.

- [ ] **Step 4: Verify and commit**

```powershell
cd frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk npm run build
rtk git add src/lib/query-segments.ts src/lib/__tests__/query-segments.test.ts 'src/app/view/[token]/scan/page.tsx' 'src/app/view/[token]/competitors/page.tsx' 'src/app/(admin)/clients/[id]/scan/ScanClient.tsx'
rtk git commit -m "feat: summarize query evidence before drill-down"
```

---

### Task 7: Verify Phase 1 route compatibility and visual quality

**Files:**
- Modify only when verification exposes a Phase 1 regression.

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: evidence that old URLs still resolve and new summaries do not hide data.

- [ ] **Step 1: Run backend and frontend verification**

```powershell
cd backend
rtk pytest tests -q
cd ../frontend
rtk npx vitest run --project unit
rtk npm run typecheck
rtk npm run build
```

- [ ] **Step 2: Verify legacy routes**

Confirm HTTP 200 for all current admin client routes and public `/scan`,
`/competitors`, `/content-plan`, `/progress`, and `/reports` routes.

- [ ] **Step 3: Capture matched desktop and mobile screenshots**

Capture admin Command Center, public Overview, public Visibility, public
Reputation, and mobile public navigation. Inspect overflow, hierarchy, empty
states, typography, focus, and evidence drill-down behavior.

- [ ] **Step 4: Record the release gate**

Phase 1 passes only when old routes remain available, no client-view whitelist
regresses, all raw evidence remains reachable, and desktop/mobile verification
commands pass.

