# Home Landing Page — Design

Date: 2026-08-12
Status: Approved for planning

## Summary

Add a new **Home** page as the first thing an admin sees after login. It shows a
time-of-day greeting addressed to the admin, a one-line summary stat, and an
**Action Required** inbox of pending work grouped by the existing Review Queue
buckets. Home becomes the new landing route; the existing Dashboard is unchanged
and stays reachable from the sidebar.

This is a presentation-only feature over data SeenBy already computes. No new
tables, no backend endpoints, no score or language-rule changes.

## Goals

- Give the admin a focused "what needs me right now" first screen on login.
- Reuse the Review Queue's pending-work computation so the two surfaces cannot
  drift.
- Keep the deep analytics Dashboard exactly as it is.

## Non-goals

- No new backend/API work. No new outcome-action states or buckets.
- No client-facing surface changes (Home is admin-only, inside `(admin)`).
- No changes to Review Queue behaviour beyond extracting its bucket logic into a
  shared module.

## Decisions (resolved during brainstorming)

1. **Home vs Dashboard:** Home is a *new* landing page at `/home`; Dashboard is
   kept as-is. Not a merge/replace.
2. **Action Required source:** Reuse the Review Queue's five outcome-action
   buckets (Accuracy review, Client approval, Publish-ready, Verification-ready,
   Overdue). No ops/attention items on Home.
3. **Greeting name:** Sourced from a new `ADMIN_DISPLAY_NAME` env var, falling
   back to `"Admin"`. No name hardcoded in source.
4. **Greeting card content:** Salutation + subtitle + one-line summary stat
   derived from the action buckets (total items + distinct client count).

## Route & landing switch

- New page: `frontend/src/app/(admin)/home/page.tsx` — server component,
  `export const dynamic = "force-dynamic"`, inside the `(admin)` route group so
  it inherits the sidebar + auth layout (which already redirects to
  `/auth/login` when there is no session).
- Repoint the three existing `/dashboard` landing redirects to `/home`:
  - `frontend/src/app/page.tsx` — `redirect("/dashboard")` → `redirect("/home")`
  - `frontend/src/middleware.ts` (~line 67) — logged-in user hitting
    `/auth/login` is redirected to `/dashboard` → `/home`
  - `frontend/src/app/auth/login/page.tsx` (~line 29) — `signIn` `callbackUrl:
    "/dashboard"` → `"/home"`
- `/dashboard` itself is untouched and remains a sidebar destination.

## Sidebar navigation

- `frontend/src/lib/navigation.ts`: add `{ href: "/home", label: "Home" }` as
  the **first** entry of `ADMIN_GLOBAL_NAV` (above `/dashboard`).
- `frontend/src/components/layout/Sidebar.tsx`: add `"/home": Home` to
  `GLOBAL_NAV_ICONS` using the lucide `Home` icon (add to the import list).
- `nav-icon-coverage.test.ts` already asserts every nav `href` has an icon, so a
  missing icon fails the suite — the icon entry is mandatory, not optional.

## Shared bucket logic (avoid drift)

The bucket-matching logic currently lives inline in
`frontend/src/app/(admin)/review-queue/page.tsx` as a `queueSections` array of
`{ title, matches(action, today) }`.

Extract it to a pure, serializable module
`frontend/src/lib/review-queue-buckets.ts`:

- `QUEUE_SECTIONS`: the five `{ title, matches }` entries, moved verbatim so
  behaviour is identical.
- `groupOutcomeActions(lists, today)`: given
  `{ client, actions }[]` and a `today` `YYYY-MM-DD` string, returns
  `{ sections: { title, items: { action, client }[] }[], totalItems,
  clientCount }`.
  - `totalItems` = the sum of bucket item counts, i.e. the number of **rendered
    rows**. The Review Queue's matchers are independent, so one action can match
    two buckets (e.g. Overdue + Accuracy review) and appear as two rows; it is
    counted once **per bucket**. This is intentional so the "Action Required
    (N)" heading equals what is visible on screen.
  - `clientCount` = the number of **distinct clients** that have at least one
    item in any bucket (deduplicated, even if a client contributes multiple
    rows).

Both `/home` and `/review-queue` import this module. `review-queue/page.tsx` is
refactored to consume `QUEUE_SECTIONS` / `groupOutcomeActions` instead of its
inline copy; its rendered output is unchanged.

Data source (unchanged, same as Review Queue today):
`getClients()` + `getAllOutcomeActions(clientId)` per client. The per-client
fetch (N+1 over clients) is inherited from Review Queue and acceptable at
single-admin scale.

## Page layout — `/home`

Server component fetches clients + their outcome actions, computes
`today = new Date().toISOString().slice(0, 10)`, and calls
`groupOutcomeActions(...)`.

### 1. Greeting header (card)

- A `"use client"` component `HomeGreeting` receives props: `name`,
  `totalItems`, `clientCount`.
- Time-of-day salutation is computed **browser-side** from
  `new Date().getHours()` (server is UTC / admin is GMT+8, so a server-computed
  salutation would be wrong):
  - 5–11 → "Good morning"
  - 12–17 → "Good afternoon"
  - 18–4 → "Good evening"
- To avoid a hydration mismatch, the component renders a neutral fallback
  ("Welcome back, {name}") on first paint, then resolves to the local-time
  salutation after mount (`useEffect` → `setMounted(true)`).
- Subtitle line: "Here's what needs your attention today."
- Summary stat line, derived from props:
  - `totalItems === 0` → "You're all caught up — nothing needs your attention."
  - else → "You have {totalItems} item(s) needing attention across
    {clientCount} client(s)." (correct singular/plural).

### 2. Action Required (N)

- Section heading "Action Required" with the total count `N = totalItems`.
- Render each non-empty bucket as a labelled group (bucket title + count badge),
  matching the Review Queue's card/row styling:
  - Row: action title (truncated), client name + `· Due {due_date}` when
    present, and a priority badge.
  - Row links to `/clients/{client.id}/delivery` (same target as Review Queue).
- Empty buckets are omitted.
- If `totalItems === 0`, show a single centered empty state ("You're all caught
  up") instead of the bucket list.
- Footer link: "View full Review Queue →" to `/review-queue`.

## Language rules

All surfaced strings comply with CLAUDE.md §2. "Action Required", the five
existing bucket titles, and the greeting copy contain no banned terms. The
`seenby-verify` banned-language scan must pass.

## Docs

Update `CLAUDE.md` §9 (Admin Panel Navigation):
- Change `/ → redirect to /dashboard` to `/ → redirect to /home`.
- Add `/home → admin home (greeting + Action Required inbox, landing page)` as
  the first global page, and adjust the `/dashboard` description so it is no
  longer described as the landing page.

## Testing

- `navigation.test.ts` / `nav-icon-coverage.test.ts`: the new `/home` item is
  covered by the existing invariants (label present, icon present). Extend
  fixtures/expectations if the tests enumerate a fixed list.
- New unit test for `review-queue-buckets.ts`:
  - `groupOutcomeActions` groups actions into the correct buckets.
  - `totalItems` equals the sum of bucket item counts (rendered rows).
  - `clientCount` counts distinct clients, not distinct items — a client with
    rows in two buckets counts once.
  - An action matching two buckets (e.g. overdue + accuracy) appears in both and
    is counted once per bucket, preserving the Review Queue's pre-extraction
    behaviour.
- Manual/verify: `/`, post-login, and logged-in-hitting-login all land on
  `/home`; Home renders greeting + buckets; empty state shows when no actions;
  Review Queue output is unchanged after the refactor.

## Files touched

New:
- `frontend/src/app/(admin)/home/page.tsx`
- `frontend/src/app/(admin)/home/HomeGreeting.tsx`
- `frontend/src/lib/review-queue-buckets.ts`
- `frontend/src/lib/__tests__/review-queue-buckets.test.ts`

Modified:
- `frontend/src/app/page.tsx` (redirect target)
- `frontend/src/middleware.ts` (redirect target)
- `frontend/src/app/auth/login/page.tsx` (callbackUrl)
- `frontend/src/lib/navigation.ts` (nav item)
- `frontend/src/components/layout/Sidebar.tsx` (icon)
- `frontend/src/app/(admin)/review-queue/page.tsx` (consume shared module)
- `frontend/auth.ts` (`ADMIN_DISPLAY_NAME` → session `name`)
- `CLAUDE.md` (§9 navigation)
