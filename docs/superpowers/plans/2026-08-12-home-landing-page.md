# Home Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/home` landing page showing a time-of-day greeting plus an "Action Required" inbox of pending outcome actions, and make it the post-login landing route.

**Architecture:** Presentation-only over data SeenBy already computes. The Review Queue's bucket logic is extracted into a shared, unit-tested module that both `/review-queue` and the new `/home` consume, so they cannot drift. Greeting time-of-day is resolved client-side (server runs UTC; admin is GMT+8). No backend, schema, or scoring changes.

**Tech Stack:** Next.js 15 (App Router, `(admin)` route group, server components), React 19, next-auth v5 (credentials, single admin), Tailwind + shadcn/ui primitives (`Card`, `Badge`, `Button`, `Link`), lucide-react icons, Vitest (node "unit" project).

## Global Constraints

- **Frontend dir:** all paths below are under `frontend/` unless stated. Run all commands from `frontend/`.
- **Unit test project:** the node unit project only includes `src/lib/__tests__/**/*.test.ts`. Pure logic that needs a unit test must live under `src/lib/`.
- **Unit test command:** `npx vitest run --project unit` (optionally append a file path to scope it).
- **Typecheck:** `npm run typecheck`. **Build:** `npm run build`.
- **Language rules (CLAUDE.md §2):** never surface banned terms (cited/uncited, mentioned, citation rate, ranking position, confidence score, char offset, token count, etc.) in any UI string. All copy in this plan is pre-checked compliant — do not introduce new client-facing wording without re-checking.
- **API access rule (CLAUDE.md §10):** all API calls go through `src/lib/api.ts`; never fetch directly in components.
- **Commit trailer:** end every commit message body with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Do not run scheduled scans or touch backend** — this is a frontend-only change.

---

### Task 1: Shared review-queue bucket module (+ refactor Review Queue to use it)

Extract the pending-work bucket logic that currently lives inline in `review-queue/page.tsx` into a pure, serializable module. This is the single source of truth for both `/review-queue` and `/home`.

**Files:**
- Create: `src/lib/review-queue-buckets.ts`
- Test: `src/lib/__tests__/review-queue-buckets.test.ts`
- Modify: `src/app/(admin)/review-queue/page.tsx`

**Interfaces:**
- Consumes: `OutcomeAction` from `@/types`.
- Produces:
  - `interface QueueClient { id: string; name: string }`
  - `interface QueueItem { action: OutcomeAction; client: QueueClient }`
  - `interface GroupedQueueSection { title: string; items: QueueItem[] }`
  - `interface GroupedQueue { sections: GroupedQueueSection[]; totalItems: number; clientCount: number }`
  - `const QUEUE_SECTIONS` (the five bucket defs)
  - `function groupOutcomeActions(lists: { client: QueueClient; actions: OutcomeAction[] }[], today: string): GroupedQueue`
  - `totalItems` = sum of every section's item count (rendered rows; one action can match two buckets and count once per bucket). `clientCount` = distinct client ids across all rows. `sections` always contains all five buckets in fixed order, including empty ones.

- [ ] **Step 1: Write the failing test**

Create `src/lib/__tests__/review-queue-buckets.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import type { OutcomeAction } from "@/types"
import { QUEUE_SECTIONS, groupOutcomeActions } from "@/lib/review-queue-buckets"

const TODAY = "2026-08-12"

function makeAction(overrides: Partial<OutcomeAction>): OutcomeAction {
  return {
    id: "a1",
    client_id: "c1",
    scan_id: null,
    work_log_entry_id: null,
    content_deliverable_id: null,
    source_kind: "scan",
    source_ref: null,
    title: "Untitled",
    rationale: "",
    action_type: "content",
    priority: "medium",
    priority_score: null,
    priority_reasons: null,
    confidence: "medium",
    status: "detected",
    owner: null,
    due_date: null,
    destination_url: null,
    client_safe_summary: null,
    verification_result: null,
    published_at: null,
    verified_at: null,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  }
}

function titles(): string[] {
  return QUEUE_SECTIONS.map((s) => s.title)
}

describe("groupOutcomeActions", () => {
  it("returns all five buckets in fixed order, including empties", () => {
    const { sections } = groupOutcomeActions([], TODAY)
    expect(sections.map((s) => s.title)).toEqual([
      "Accuracy review",
      "Client approval",
      "Publish-ready",
      "Verification-ready",
      "Overdue",
    ])
    expect(titles()).toEqual(sections.map((s) => s.title))
  })

  it("is empty for no actions", () => {
    const grouped = groupOutcomeActions(
      [{ client: { id: "c1", name: "Acme" }, actions: [] }],
      TODAY,
    )
    expect(grouped.totalItems).toBe(0)
    expect(grouped.clientCount).toBe(0)
    expect(grouped.sections.every((s) => s.items.length === 0)).toBe(true)
  })

  it("routes each status to its bucket", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({ id: "acc", action_type: "accuracy_review", status: "detected" }),
            makeAction({ id: "cli", status: "waiting_client" }),
            makeAction({ id: "pub", status: "ready_to_publish" }),
            makeAction({ id: "ver", status: "waiting_verification" }),
          ],
        },
      ],
      TODAY,
    )
    const by = Object.fromEntries(grouped.sections.map((s) => [s.title, s.items.map((i) => i.action.id)]))
    expect(by["Accuracy review"]).toEqual(["acc"])
    expect(by["Client approval"]).toEqual(["cli"])
    expect(by["Publish-ready"]).toEqual(["pub"])
    expect(by["Verification-ready"]).toEqual(["ver"])
  })

  it("counts an action that matches two buckets once per bucket", () => {
    // accuracy_review + detected + past due_date → Accuracy review AND Overdue.
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({
              id: "dbl",
              action_type: "accuracy_review",
              status: "detected",
              due_date: "2026-08-01",
            }),
          ],
        },
      ],
      TODAY,
    )
    const accuracy = grouped.sections.find((s) => s.title === "Accuracy review")!
    const overdue = grouped.sections.find((s) => s.title === "Overdue")!
    expect(accuracy.items.map((i) => i.action.id)).toEqual(["dbl"])
    expect(overdue.items.map((i) => i.action.id)).toEqual(["dbl"])
    expect(grouped.totalItems).toBe(2) // two rendered rows
    expect(grouped.clientCount).toBe(1) // one distinct client
  })

  it("excludes terminal-status actions from Overdue", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [makeAction({ id: "done", status: "verified", due_date: "2026-08-01" })],
        },
      ],
      TODAY,
    )
    expect(grouped.sections.find((s) => s.title === "Overdue")!.items).toHaveLength(0)
    expect(grouped.totalItems).toBe(0)
  })

  it("counts distinct clients, not rows", () => {
    const grouped = groupOutcomeActions(
      [
        {
          client: { id: "c1", name: "Acme" },
          actions: [
            makeAction({ id: "x", status: "waiting_client" }),
            makeAction({ id: "y", status: "ready_to_publish" }),
          ],
        },
      ],
      TODAY,
    )
    expect(grouped.totalItems).toBe(2)
    expect(grouped.clientCount).toBe(1)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run --project unit src/lib/__tests__/review-queue-buckets.test.ts`
Expected: FAIL — cannot resolve `@/lib/review-queue-buckets` (module not created yet).

- [ ] **Step 3: Create the module**

Create `src/lib/review-queue-buckets.ts`:

```ts
// Shared pending-work buckets for /review-queue and /home. Pure and
// serializable — no React. Matchers are independent: one action can match more
// than one bucket (e.g. Overdue + Accuracy review) and appears as a row in each.
import type { OutcomeAction } from "@/types"

/** Minimal client shape the queue needs — decoupled from the full Client type. */
export interface QueueClient {
  id: string
  name: string
}

export interface QueueItem {
  action: OutcomeAction
  client: QueueClient
}

export interface QueueSectionDef {
  title: string
  matches: (action: OutcomeAction, today: string) => boolean
}

export interface GroupedQueueSection {
  title: string
  items: QueueItem[]
}

export interface GroupedQueue {
  /** All buckets in fixed order, including empty ones. */
  sections: GroupedQueueSection[]
  /** Sum of every bucket's item count (rendered rows). */
  totalItems: number
  /** Distinct clients contributing at least one row to any bucket. */
  clientCount: number
}

export const QUEUE_SECTIONS: readonly QueueSectionDef[] = [
  {
    title: "Accuracy review",
    matches: (action) =>
      action.action_type === "accuracy_review" &&
      ["detected", "recommended", "approved_internal"].includes(action.status),
  },
  {
    title: "Client approval",
    matches: (action) => action.status === "waiting_client",
  },
  {
    title: "Publish-ready",
    matches: (action) => action.status === "ready_to_publish",
  },
  {
    title: "Verification-ready",
    matches: (action) => action.status === "waiting_verification",
  },
  {
    title: "Overdue",
    matches: (action, today) =>
      Boolean(
        action.due_date &&
          action.due_date < today &&
          !["verified", "no_change", "superseded", "dismissed"].includes(action.status),
      ),
  },
] as const

export function groupOutcomeActions(
  lists: { client: QueueClient; actions: OutcomeAction[] }[],
  today: string,
): GroupedQueue {
  const sections: GroupedQueueSection[] = QUEUE_SECTIONS.map((section) => ({
    title: section.title,
    items: lists.flatMap(({ client, actions }) =>
      actions
        .filter((action) => section.matches(action, today))
        .map((action) => ({ action, client })),
    ),
  }))

  const totalItems = sections.reduce((sum, section) => sum + section.items.length, 0)
  const clientIds = new Set<string>()
  for (const section of sections) {
    for (const item of section.items) {
      clientIds.add(item.client.id)
    }
  }

  return { sections, totalItems, clientCount: clientIds.size }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run --project unit src/lib/__tests__/review-queue-buckets.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Refactor the Review Queue page to consume the module**

Replace the entire contents of `src/app/(admin)/review-queue/page.tsx` with:

```tsx
import Link from "next/link"
import { getAllOutcomeActions, getClients } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { groupOutcomeActions } from "@/lib/review-queue-buckets"

export default async function ReviewQueuePage() {
  const clients = await getClients()
  const lists = await Promise.all(
    clients.map(async (client) => ({ client, actions: await getAllOutcomeActions(client.id) })),
  )
  const today = new Date().toISOString().slice(0, 10)
  const { sections } = groupOutcomeActions(lists, today)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">Review Queue</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Outcome actions that need an operating decision.
        </p>
      </div>
      {sections.map((section) => (
        <section key={section.title}>
          <div className="mb-2 flex items-center justify-between border-b pb-2">
            <h2 className="text-sm font-semibold">{section.title}</h2>
            <Badge variant="secondary">{section.items.length}</Badge>
          </div>
          {section.items.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No actions in this section.</p>
          ) : (
            <div className="divide-y rounded-md border bg-card">
              {section.items.map(({ action, client }) => (
                <Link
                  key={action.id}
                  href={`/clients/${client.id}/delivery`}
                  className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-muted/30"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{action.title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {client.name}
                      {action.due_date ? ` · Due ${action.due_date}` : ""}
                    </p>
                  </div>
                  <Badge variant="outline">{action.priority}</Badge>
                </Link>
              ))}
            </div>
          )}
        </section>
      ))}
      <div className="border-t pt-4">
        <Button variant="outline" size="sm" asChild>
          <Link href="/review-queue/legacy-work-log">Legacy work-log suggestions</Link>
        </Button>
      </div>
    </div>
  )
}
```

Note: this preserves the page's rendered output exactly (all five sections, empty ones show "No actions in this section.", same row markup, same footer link). Only the bucket logic moved.

- [ ] **Step 6: Typecheck**

Run: `npm run typecheck`
Expected: PASS (no errors). The old inline `queueSections` const and the now-unused `OutcomeAction` type import are gone; there should be no unused-import errors.

- [ ] **Step 7: Commit**

```bash
git add src/lib/review-queue-buckets.ts src/lib/__tests__/review-queue-buckets.test.ts "src/app/(admin)/review-queue/page.tsx"
git commit -m "$(cat <<'EOF'
refactor(review-queue): extract shared outcome-action buckets

Pure groupOutcomeActions/QUEUE_SECTIONS module so /home and /review-queue
share one source of truth. Review Queue output unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Greeting salutation helper

A pure function mapping a local hour to a salutation, unit-tested. Kept in `src/lib/` so the node unit project can test it (the `HomeGreeting` React component in Task 5 imports it).

**Files:**
- Create: `src/lib/greeting.ts`
- Test: `src/lib/__tests__/greeting.test.ts`

**Interfaces:**
- Produces: `function salutationForHour(hour: number): string` returning `"Good morning"` (5–11), `"Good afternoon"` (12–17), or `"Good evening"` (18–4).

- [ ] **Step 1: Write the failing test**

Create `src/lib/__tests__/greeting.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { salutationForHour } from "@/lib/greeting"

describe("salutationForHour", () => {
  it("says good morning from 5 to 11", () => {
    expect(salutationForHour(5)).toBe("Good morning")
    expect(salutationForHour(11)).toBe("Good morning")
  })
  it("says good afternoon from 12 to 17", () => {
    expect(salutationForHour(12)).toBe("Good afternoon")
    expect(salutationForHour(17)).toBe("Good afternoon")
  })
  it("says good evening from 18 through the night to 4", () => {
    expect(salutationForHour(18)).toBe("Good evening")
    expect(salutationForHour(23)).toBe("Good evening")
    expect(salutationForHour(0)).toBe("Good evening")
    expect(salutationForHour(4)).toBe("Good evening")
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run --project unit src/lib/__tests__/greeting.test.ts`
Expected: FAIL — cannot resolve `@/lib/greeting`.

- [ ] **Step 3: Create the helper**

Create `src/lib/greeting.ts`:

```ts
/**
 * Time-of-day salutation for a local hour (0–23). Bands:
 * 5–11 morning, 12–17 afternoon, everything else evening.
 */
export function salutationForHour(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning"
  if (hour >= 12 && hour < 18) return "Good afternoon"
  return "Good evening"
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run --project unit src/lib/__tests__/greeting.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/greeting.ts src/lib/__tests__/greeting.test.ts
git commit -m "$(cat <<'EOF'
feat(home): add salutationForHour greeting helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Env-driven admin display name

Make the session's display name configurable so the greeting can address the admin by name (`Faris`) without hardcoding it. Fallback stays `"Admin"`.

**Files:**
- Modify: `auth.ts` (frontend root, line ~91)

**Interfaces:**
- Produces: session `user.name` resolves to `process.env.ADMIN_DISPLAY_NAME || "Admin"`. Consumed by Task 6 (`HomePage` reads `session.user.name`).

- [ ] **Step 1: Edit the authorize return**

In `auth.ts`, change the success return (currently `return { id: "admin", name: "Admin", email: "admin@seenby.my" }`) to:

```ts
          return {
            id: "admin",
            name: process.env.ADMIN_DISPLAY_NAME || "Admin",
            email: "admin@seenby.my",
          }
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add auth.ts
git commit -m "$(cat <<'EOF'
feat(auth): source admin display name from ADMIN_DISPLAY_NAME env

Falls back to "Admin". Lets the Home greeting address the admin by name
without hardcoding it.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

Note for the operator: to show "Faris", set `ADMIN_DISPLAY_NAME=Faris` in the frontend service env (Railway). Not required for the code to work — it degrades to "Admin".

---

### Task 4: Sidebar nav item + icon (+ nav test + brand link)

Add "Home" as the first global nav item with an icon, update the navigation contract test, and point the sidebar brand logo at `/home`.

**Files:**
- Modify: `src/lib/navigation.ts`
- Modify: `src/components/layout/Sidebar.tsx`
- Modify: `src/lib/__tests__/navigation.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ADMIN_GLOBAL_NAV` begins with `{ href: "/home", label: "Home" }`; `GLOBAL_NAV_ICONS["/home"]` is defined.

- [ ] **Step 1: Update the navigation contract test first (expected to fail)**

In `src/lib/__tests__/navigation.test.ts`, update the global-destinations assertion to include `/home` first:

```ts
  it("exposes the global (non-client-scoped) admin destinations", () => {
    expect(ADMIN_GLOBAL_NAV.map((item) => item.href)).toEqual([
      "/home",
      "/dashboard",
      "/clients",
      "/gap-matrix",
      "/benchmarks",
      "/review-queue",
    ])
  })
```

- [ ] **Step 2: Run nav tests to verify failure**

Run: `npx vitest run --project unit src/lib/__tests__/navigation.test.ts src/lib/__tests__/nav-icon-coverage.test.ts`
Expected: FAIL — `navigation.test.ts` expects `/home` in the array (not there yet); `nav-icon-coverage.test.ts` still passes at this point.

- [ ] **Step 3: Add the nav item**

In `src/lib/navigation.ts`, make `/home` the first entry of `ADMIN_GLOBAL_NAV`:

```ts
export const ADMIN_GLOBAL_NAV: readonly NavItem[] = [
  // Post-login landing: greeting + Action Required inbox. Home icon in Sidebar.
  { href: "/home", label: "Home" },
  // Landing page: the cross-client "what happened" view. LayoutDashboard is
  // taken by the per-client Overview item — Sidebar uses Radar here.
  { href: "/dashboard", label: "Dashboard" },
  { href: "/clients", label: "All Clients" },
  { href: "/gap-matrix", label: "Portfolio Intelligence" },
  // Phase 6. Global rather than client-scoped: it compares the whole portfolio
  // against cohorts, so it does not belong in CLIENT_NAV_GROUPS' Intelligence
  // group (those hrefs are relative to /clients/[id]).
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/review-queue", label: "Review Queue" },
] as const
```

- [ ] **Step 4: Add the icon and point the brand at /home**

In `src/components/layout/Sidebar.tsx`:

(a) add `Home` to the lucide import list (alongside `LayoutDashboard`, etc.):

```ts
import {
  LayoutDashboard,
  Home,
  ListChecks,
  Search,
```

(b) add `/home` as the first entry of `GLOBAL_NAV_ICONS`:

```ts
export const GLOBAL_NAV_ICONS: Record<string, IconType> = {
  "/home": Home,
  "/dashboard": Radar,
  "/clients": Users,
  "/gap-matrix": Table2,
  "/benchmarks": Gauge,
  "/review-queue": Inbox,
}
```

(c) point the brand link at the new landing (the app's home is now `/home`). In `Brand()`, change `<Link href="/dashboard" ...>` to `<Link href="/home" ...>`.

- [ ] **Step 5: Run nav tests to verify they pass**

Run: `npx vitest run --project unit src/lib/__tests__/navigation.test.ts src/lib/__tests__/nav-icon-coverage.test.ts`
Expected: PASS. `nav-icon-coverage` confirms `/home` has an icon and no stale icon entries exist.

- [ ] **Step 6: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/lib/navigation.ts src/components/layout/Sidebar.tsx src/lib/__tests__/navigation.test.ts
git commit -m "$(cat <<'EOF'
feat(nav): add Home as the first global nav destination

Home icon, first in ADMIN_GLOBAL_NAV, brand logo now links to /home.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: HomeGreeting client component

The greeting header card. Salutation is resolved on the client after mount because the server runs UTC and the admin is GMT+8; a neutral greeting renders until mount to avoid a hydration mismatch.

**Files:**
- Create: `src/app/(admin)/home/HomeGreeting.tsx`

**Interfaces:**
- Consumes: `salutationForHour` from `@/lib/greeting` (Task 2).
- Produces: `export function HomeGreeting(props: { name: string; totalItems: number; clientCount: number })`. Consumed by Task 6.

- [ ] **Step 1: Create the component**

Create `src/app/(admin)/home/HomeGreeting.tsx`:

```tsx
"use client"

import { useEffect, useState } from "react"
import { salutationForHour } from "@/lib/greeting"

interface Props {
  name: string
  totalItems: number
  clientCount: number
}

/**
 * Greeting header. The salutation depends on the admin's LOCAL time, so it is
 * resolved on the client after mount — the server runs UTC and would render the
 * wrong time of day. Until mounted we show a neutral greeting to avoid a
 * hydration mismatch between server and client HTML.
 */
export function HomeGreeting({ name, totalItems, clientCount }: Props) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const greeting = mounted
    ? `${salutationForHour(new Date().getHours())}, ${name}`
    : `Welcome back, ${name}`

  const summary =
    totalItems === 0
      ? "You're all caught up — nothing needs your attention."
      : `You have ${totalItems} item${totalItems === 1 ? "" : "s"} needing attention across ` +
        `${clientCount} client${clientCount === 1 ? "" : "s"}.`

  return (
    <div className="rounded-xl border bg-card p-6 shadow-sm">
      <h1 className="font-display text-2xl font-bold tracking-tight">{greeting}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Here&apos;s what needs your attention today.
      </p>
      <p className="mt-3 text-sm font-medium">{summary}</p>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add "src/app/(admin)/home/HomeGreeting.tsx"
git commit -m "$(cat <<'EOF'
feat(home): add HomeGreeting header component

Client-resolved local-time salutation with hydration-safe fallback and a
summary stat.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Home page (server component)

Fetch clients + their outcome actions, group them via the shared module, and render the greeting plus the Action Required inbox.

**Files:**
- Create: `src/app/(admin)/home/page.tsx`

**Interfaces:**
- Consumes: `auth` from `../../../../auth`; `getClients`, `getAllOutcomeActions` from `@/lib/api`; `groupOutcomeActions` from `@/lib/review-queue-buckets` (Task 1); `HomeGreeting` from `./HomeGreeting` (Task 5); `Badge` from `@/components/ui/badge`.
- Produces: the `/home` route (default export `HomePage`).

- [ ] **Step 1: Create the page**

Create `src/app/(admin)/home/page.tsx`:

```tsx
// frontend/src/app/(admin)/home/page.tsx
// Admin home — the post-login landing. Greeting + the pending-work inbox (same
// buckets as /review-queue). Server component: the data fetch is server-side
// (api.ts is server-only) and filters/session are read on the server.
import Link from "next/link"
import { auth } from "../../../../auth"
import { getAllOutcomeActions, getClients } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { groupOutcomeActions } from "@/lib/review-queue-buckets"
import { HomeGreeting } from "./HomeGreeting"

export const dynamic = "force-dynamic"

export default async function HomePage() {
  const session = await auth()
  const name = session?.user?.name ?? "Admin"

  const clients = await getClients()
  const lists = await Promise.all(
    clients.map(async (client) => ({ client, actions: await getAllOutcomeActions(client.id) })),
  )
  const today = new Date().toISOString().slice(0, 10)
  const { sections, totalItems, clientCount } = groupOutcomeActions(lists, today)
  const activeSections = sections.filter((section) => section.items.length > 0)

  return (
    <div className="space-y-6">
      <HomeGreeting name={name} totalItems={totalItems} clientCount={clientCount} />

      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold tracking-tight">
          Action Required{totalItems > 0 ? ` (${totalItems})` : ""}
        </h2>
        <Link href="/review-queue" className="text-sm text-primary hover:underline">
          View full Review Queue →
        </Link>
      </div>

      {totalItems === 0 ? (
        <div className="rounded-md border bg-card py-12 text-center">
          <p className="text-sm text-muted-foreground">
            You&apos;re all caught up. Nothing needs your attention.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {activeSections.map((section) => (
            <section key={section.title}>
              <div className="mb-2 flex items-center justify-between border-b pb-2">
                <h3 className="text-sm font-semibold">{section.title}</h3>
                <Badge variant="secondary">{section.items.length}</Badge>
              </div>
              <div className="divide-y rounded-md border bg-card">
                {section.items.map(({ action, client }) => (
                  <Link
                    key={action.id}
                    href={`/clients/${client.id}/delivery`}
                    className="flex items-center justify-between gap-4 px-4 py-3 transition-colors hover:bg-muted/30"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{action.title}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {client.name}
                        {action.due_date ? ` · Due ${action.due_date}` : ""}
                      </p>
                    </div>
                    <Badge variant="outline">{action.priority}</Badge>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
```

Note on the `auth` import path: `../../../../auth` climbs `home → (admin) → app → src → frontend`, reaching `frontend/auth.ts` (four levels — one more than `layout.tsx`, which sits one directory shallower). If the typecheck in Step 2 reports the module can't be found, verify the depth against `layout.tsx`'s `../../../auth`.

- [ ] **Step 2: Typecheck**

Run: `npm run typecheck`
Expected: PASS. Confirms the `auth` import path resolves and all props/types line up.

- [ ] **Step 3: Commit**

```bash
git add "src/app/(admin)/home/page.tsx"
git commit -m "$(cat <<'EOF'
feat(home): add /home landing page with Action Required inbox

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Switch the landing redirects to /home

Point the three existing `/dashboard` landing redirects at `/home`. Dashboard itself stays reachable via the sidebar.

**Files:**
- Modify: `src/app/page.tsx`
- Modify: `src/middleware.ts` (~line 67)
- Modify: `src/app/auth/login/page.tsx` (~line 29)

**Interfaces:** none produced/consumed by later tasks.

- [ ] **Step 1: Root redirect**

In `src/app/page.tsx`, change `redirect("/dashboard")` to `redirect("/home")`.

- [ ] **Step 2: Middleware redirect for logged-in users hitting login**

In `src/middleware.ts`, in the `if (isLoggedIn && isLoginPage)` branch, change:

```ts
    return NextResponse.redirect(new URL("/home", req.nextUrl))
```

- [ ] **Step 3: Post-login callback URL**

In `src/app/auth/login/page.tsx`, change `callbackUrl: "/dashboard"` to `callbackUrl: "/home"`.

- [ ] **Step 4: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/page.tsx src/middleware.ts src/app/auth/login/page.tsx
git commit -m "$(cat <<'EOF'
feat(home): make /home the post-login landing route

Root redirect, logged-in-hitting-login redirect, and signIn callbackUrl all
point to /home. Dashboard stays reachable from the sidebar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Docs + full verification

Update the canonical navigation doc and run the project's definition-of-done gate.

**Files:**
- Modify: `CLAUDE.md` (§9 Admin Panel Navigation) — repo root, i.e. `../CLAUDE.md` from `frontend/`.

- [ ] **Step 1: Update CLAUDE.md §9**

In the project-root `CLAUDE.md`, section 9, change the first two route lines from:

```
/                        → redirect to /dashboard
/dashboard               → global activity dashboard (feed + attention/health/cost tiles, landing page)
```

to:

```
/                        → redirect to /home
/home                    → admin home (greeting + Action Required inbox, post-login landing page)
/dashboard               → global activity dashboard (feed + attention/health/cost tiles)
```

Leave the rest of §9 (route group explanation, client-scoped routes, view routes) unchanged.

- [ ] **Step 2: Run the full unit suite**

Run (from `frontend/`): `npx vitest run --project unit`
Expected: PASS — `review-queue-buckets`, `greeting`, `navigation`, `nav-icon-coverage`, and all pre-existing lib tests green.

- [ ] **Step 3: Typecheck and build**

Run: `npm run typecheck`
Then: `npm run build`
Expected: both PASS; the build lists `/home` among the routes.

- [ ] **Step 4: Banned-language + definition-of-done gate**

Invoke the `seenby-verify` skill and follow it (backend tests, frontend typecheck/build, banned-language scan, migration sanity). This change is frontend-only and adds no banned terms, so the language scan must be clean. Fix anything it flags before finishing.

- [ ] **Step 5: Commit**

```bash
git add ../CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(nav): record /home as the landing route in CLAUDE.md §9

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Manual verification (browser)**

Start the app (run-app skill / dev server) and confirm:
- Visiting `/` redirects to `/home`.
- Signing in lands on `/home`; visiting `/auth/login` while logged in redirects to `/home`.
- Home shows the greeting (morning/afternoon/evening + name), the summary stat, and the Action Required buckets; empty buckets are hidden.
- With no pending actions, the "You're all caught up" empty state shows.
- Clicking an item opens that client's `/delivery` page; "View full Review Queue →" opens `/review-queue`, which looks identical to before.
- The sidebar shows "Home" first with its icon; the brand logo links to `/home`.

---

## Notes / risks

- **N+1 fetch:** `/home` fetches outcome actions per client, inherited from `/review-queue`. Fine at single-admin scale; if client count grows large this is the first thing to batch (out of scope here).
- **Session name:** `HomePage` reads `session.user.name`, whose value comes from `ADMIN_DISPLAY_NAME` (Task 3). Unset → "Admin".
- **No backend/schema/scoring changes**, so no Alembic migration and no `SCORE_VERSION` bump.
