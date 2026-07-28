# Core / Premium Packaging + Client-View Gating

> Status: **Design parked for later** — not yet implemented.
> Scope of this doc: (1) what each tier sells, (2) how to gate the client-facing
> portal so each client only sees what their package includes.

---

## Part 1 — The packaging (what each tier sells)

Three things to sell: a one-time **Audit** (front door), then a **Core** or
**Premium** monthly retainer. Each tier sells a different verb:

- **Audit = SEE the problem** (one-time diagnostic, creates urgency)
- **Core = MEASURE + MAINTAIN** (track the score, basic fixes, prove progress)
- **Premium = WIN** (actively close gaps with content + strategy + reputational protection)

Indicative pricing (KL / Malaysia, medical-first niche):
- **Audit** — one-time RM 1,500 (credited to month 1 if they sign)
- **Core** — RM 2,500–3,500/mo
- **Premium** — RM 4,500–6,000/mo

Capacity is 5–10 clients solo, so price high — never fill a slot below ~RM 2,500.
Target mix ≈ 2 Core + 4 Premium ≈ RM 23k–28k/mo.

### Deliverable map

| Deliverable (from the app) | Audit (one-time) | Core | Premium |
|---|---|---|---|
| AI Visibility Scan | 1 snapshot, all 4 platforms | Monthly, enabled platforms | Bi-weekly, all 4 |
| GEO Score + 5-dimension breakdown | ✓ snapshot | ✓ tracked monthly | ✓ tracked + percentile |
| Competitors tracked (Win/Loss board) | up to 3 | up to 3 | up to 5 |
| Competitor overtake alerts | — | ✓ | ✓ |
| GEO Action Center (3–5 priorities) | ✓ one-time | ✓ monthly | ✓ monthly |
| AI Readiness Toolkit (llms/schema/robots) | files + guide (DIY) | done-for-you + verified | done-for-you + maintained |
| Content Gap analysis | — | ✓ | ✓ |
| 90-Day Content Roadmap + drafted articles | — | — | ✓ (refreshed quarterly) |
| On-demand content briefs | — | — | ✓ |
| Weekly digest email | — | ✓ | ✓ |
| Monthly PDF report ("what changed") | ✓ (the deliverable) | ✓ | ✓ |
| Client read-only portal link | a taste | ✓ | ✓ |
| AI referral traffic tracking | — | ✓ | ✓ |
| AI misinformation monitoring (hallucination flags) | — | — | ✓ |
| Monthly strategy call | audit walkthrough | email-only | ✓ live call/Loom |

**Medical anchor:** gate AI misinformation monitoring to Premium. For a clinic,
"protect how AI represents you factually" reframes the upgrade from *more
marketing* to *reputational safety* — that single line justifies RM 2.5k → RM 5k.

**Deliberate line:** Core tells them *what's* missing (content gaps); Premium
hands them the *written plan* to fix it (90-day roadmap + drafted articles).
Keep that split clean — it's the main reason to choose Premium.

---

## Part 2 — Client-view gating (implementation design)

### Decisions locked
- **Gating scope:** client view only. Admin always sees/runs everything.
- **Core view depth:** light gating. Core sees score, scan, competitors,
  history, reports. Premium-only = **Content Plan tab** + **benchmark section**.
- **Plan values:** `core` | `premium`, default `core`. (Add `audit` later if needed.)
- **Out of scope:** admin-panel gating, delivery-automation branching, billing,
  client self-upgrade. Plan is set manually by admin.

### Tier → client-view mapping

| Client view tab | Core sees | Premium sees |
|---|---|---|
| Overview (score, dimensions, history, AI traffic) | ✓ | ✓ + industry benchmark percentile |
| Scan (Seen by AI / Not seen) | ✓ | ✓ |
| Competitors (Win/Loss) | ✓ (up to 3) | ✓ (up to 5) |
| Content Plan (90-day roadmap) | ✗ hidden | ✓ |
| Reports (PDFs) | ✓ | ✓ |

> Competitor count (3 vs 5) is governed by what the admin attaches, NOT by view
> logic. Don't add view gating for it.

### 1. Data model
Add one column to `Client` (`backend/app/models/client.py`):
`plan: Mapped[str]` — `"core"` | `"premium"`, default `"core"`. One Alembic migration.

### 2. Single source of truth — `backend/app/core/constants.py`
```python
PLAN_FEATURES = {
    "core":    {"content_plan": False, "benchmark": False},
    "premium": {"content_plan": True,  "benchmark": True},
}
```
Changing what a tier includes = editing this one dict.

### 3. Server-side enforcement (the security boundary)
Gating MUST live in the backend payload, not just the frontend — a Core share
token could otherwise hit the API directly and pull data it didn't pay for
(CLAUDE.md §9: public view is server-side whitelisted).

In `backend/app/api/v1/client_view.py`:
- **`get_overview`** — compute effective flags:
  `show_content_plan = PLAN_FEATURES[plan]["content_plan"] and roadmap_exists`
  (same for `show_benchmark`). **Omit the benchmark block entirely** from the
  payload when Core. Replace/extend the existing `has_content_plan` field with
  this plan-gated flag.
- **`get_roadmap`** — return `None` when `plan == "core"`, regardless of whether
  a roadmap exists. (Endpoint already returns `ClientViewRoadmap | None`.)

### 4. Frontend (tiny change)
- `frontend/src/app/view/[token]/layout.tsx` — pass the new gated flag
  (`overview.show_content_plan`) into `<ViewTabs>`. The existing conditional-tab
  logic in `ViewTabs.tsx` needs **zero** changes (already does
  `...(showContentPlan ? [contentPlanTab] : [])`).
- Overview page — render the benchmark section only when `overview.benchmark` is
  present (absent for Core). Verify it's null-safe.

### 5. Admin control
Add a **Plan** dropdown (Core / Premium) to `/clients/[id]/settings`, persisted
on the client. Optionally show plan as a badge on the client card + detail header.

### Effort estimate
~1 migration, 1 constant, 2 backend endpoints, 1 settings field, ~2 frontend
lines. Small.

### Touch-point reference (as of this design)
- `backend/app/models/client.py` — add `plan`
- `backend/app/core/constants.py` — add `PLAN_FEATURES`
- `backend/app/api/v1/client_view.py` — `get_overview`, `get_roadmap`
- `frontend/src/app/view/[token]/layout.tsx` — pass gated flag
- `frontend/src/components/view/ViewTabs.tsx` — already supports conditional tab
- `/clients/[id]/settings` — add Plan dropdown

---

## When revisiting
1. Confirm pricing against real close data (are clinics paying the floor?).
2. Decide if an `audit` tier value is now needed (stripped portal for audit buyers).
3. Then proceed to a written implementation plan (writing-plans) before coding.
