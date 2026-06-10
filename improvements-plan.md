# SeenBy: What to Improve + Client Portal Decision

## Context

User has 2 trial clients and wants to know (1) what needs fixing before the product is demo-ready, and (2) whether to build a client-facing portal. Full codebase audit completed across frontend and backend.

**Current state:** App is ~80% production-ready. Core features are all built. The gaps are mostly UX polish and a handful of real bugs. No major features are missing.

---

## Question 1: What to Improve

### Tier 1 — Fix Before Any Client Sees It (bugs / embarrassments)

**A. Website URL has no format validation** (`SettingsForm.tsx` line 111)
- Currently `<Input type="text" required />` — accepts "hello world" as a website
- Fix: add `type="url"` to the website input
- One-line change, catches the most common data entry mistake

**B. No global error boundaries**
- If any page throws an unexpected JS error, user sees a blank white screen
- Fix: create `frontend/src/app/error.tsx` and `frontend/src/app/clients/[id]/error.tsx`
- Each file is ~15 lines — shows a friendly "Something went wrong" card with a reload button

**C. Competitor names lack null guards** (`competitors/page.tsx` lines 75, 143)
- `{comp.name}` renders directly with no fallback — if API returns null name, shows "undefined" in the UI
- Fix: render `{comp.name ?? "Unnamed competitor"}` as fallback

**D. Industry dropdown is a native `<select>`** (`SettingsForm.tsx` lines 115-125)
- Looks visually inconsistent with the rest of the UI (shadcn inputs)
- Fix: replace with shadcn `Select` component — already installed, just needs to be wired up

### Tier 2 — Polish Before Paying Clients (1-2 hours each)

**E. Report send has no confirmation dialog**
- User clicks "Send to client" and it fires immediately with no "are you sure?"
- Fix: add an AlertDialog (shadcn, already installed) — "Send GEO report to [email]?" with Confirm / Cancel

**F. Report send error message is a dead end**
- Error says "check that this client has a contact email set in Settings" — no link
- Fix: replace with an inline link `<a href="/clients/[id]/settings">open Settings →</a>`

**G. Score drop threshold input has no tooltip**
- Label says "Score Drop Alert Threshold" — not obvious what this means
- Fix: add a small `(?)` with popover explaining "Alert fires when overall score drops below this number"

**H. Scan results table needs `overflow-x-auto`**
- Long query text overflows on narrow screens
- Fix: wrap the results table container in `<div className="overflow-x-auto">`

### Tier 3 — Nice-to-Have (when you have time)

- Add skeleton loading to the overview score ring (currently shows nothing until data loads)
- Show toast notification on clipboard copy instead of inline text swap
- Add "unsaved changes" warning when navigating away from the Settings form mid-edit
- Pagination on activity log if it grows past 100 entries

### Ops Work (not code — just setup)

These are in `pending.md` and block email + PDF features from working in production:
1. Verify `seenby.my` domain in Resend → weekly digest and report emails won't send without this
2. Set up Cloudflare R2 bucket → PDF reports can't be stored or downloaded without this
3. Replace weak `.env` secrets before going live

---

## Question 2: Do You Need a Client Portal?

**Recommendation: No, not yet. Build it when clients ask for it.**

### Why not now

You have 2 trial clients. You don't yet know what they want to see in a portal. Building it now means building something based on guesses — and a client portal is 1-2 weeks of real work (auth, data scoping, read-only permissions, separate session management).

The biggest risk: you build it, clients don't log in, you've wasted 2 weeks that could have gone to getting more clients.

### The signal to build it

Build the portal when you start hearing: *"Can I just check my score myself?"* or *"Do I have to wait for the monthly email to see updates?"*

A rough rule: **5 paying clients and 3 asking for self-serve access** is a reasonable threshold.

### What the portal would include (when you do build it)

Keep it read-only, extremely simple:
- Score dashboard (current score + trend)
- Latest report download
- Toolkit status (which files are live)
- Activity feed (what happened this month)
- **No scan trigger** — admin only, always
- Login via magic link email (no password — clients won't remember it)

What NOT to put in the portal:
- Raw scan query results (confusing without context)
- Hallucination flagging (admin task)
- Competitor editing
- Manual score inputs

### Alternative to a portal (works right now)

Instead of building a portal, you can increase perceived transparency with just emails:
- Weekly digest already does this (score + action item)
- Consider adding a monthly "score card" image embedded in the digest email
- Add a "Your [file] is now live and earning points" email when toolkit verification passes

This gives clients visibility without building a portal.

---

## Verification (after fixing Tier 1 + 2 items)

1. Open Settings for a client → type `not-a-url` in Website field → try to save → should show browser validation error
2. Open any client page → open browser console → throw a JS error manually → should see error boundary UI instead of blank screen
3. Open Competitors page → confirm no crashes if competitor has no name
4. Open Reports page → click Send → confirmation dialog should appear before email fires
5. Resize browser to mobile width → Scan results table should scroll horizontally

---

## Files to Change (Tier 1 + 2)

| File | Change |
|---|---|
| `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` | Add `type="url"` to website input; replace `<select>` with shadcn Select; add threshold tooltip |
| `frontend/src/app/error.tsx` | Create — global error boundary |
| `frontend/src/app/clients/[id]/error.tsx` | Create — client section error boundary |
| `frontend/src/app/clients/[id]/competitors/page.tsx` | Add `?? "Unnamed competitor"` null fallback |
| `frontend/src/app/clients/[id]/reports/ReportsClient.tsx` | Add AlertDialog confirmation before send; fix error message link |
| `frontend/src/app/clients/[id]/scan/ScanClient.tsx` | Wrap table in `overflow-x-auto` |
