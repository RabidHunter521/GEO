---
name: seenby-demo-check
description: Browser walkthrough that checks the known demo-quality bugs on the Medilink demo client before any pitch or client call. Verifies the 8 embarrassment-tier issues from walkthrough.md §6.1 with screenshots and reports pass/fail per item. Trigger on "demo check", "is the demo clean", "pre-pitch check", or before showing the app to anyone external.
---

# SeenBy Demo Check

Verifies the exact issues a prospect would see, from walkthrough.md §6.1 (written 5 Jul 2026). Run against the local app with the **Medilink Healthcare** demo client. Use Playwright (webapp-testing skill or playwright MCP tools). Save all screenshots to a `demo-check/` folder in the scratchpad and report a pass/fail table at the end.

## Setup

1. Start the app with the `run-app` skill (frontend :3000, backend :8000).
2. **Also start the Celery worker** (`backend/bin/start-worker.sh` or equivalent on Windows: `cd backend && poetry run celery -A workers.celery_app worker`) — check #6 requires it.
3. Log in at `http://localhost:3000/auth/login` (admin credentials from `.env` / ask Faris if unknown).
4. Open `/clients`, click Medilink Healthcare, note its client id. From its Settings page, copy the client-view share link.

## The checks (screenshot each)

| # | Where | What to verify | Bug if... |
|---|---|---|---|
| 1 | Client view Overview → "Straight From AI Search" AND monthly PDF p.2 | Proof quotes are full sentences | Quote is a fragment like `"Medilink Healthcare 2."` — junk proof quotes |
| 2 | Admin scan page headline vs client view hero | Both say the same denominator | Admin says "32 of 72", client view says "32 of 71" |
| 3 | Generate monthly report → cover page | Report period matches the scan date's data period | Titled "July 2026" for a 22-June scan (labeled by generation date) |
| 4 | Monthly PDF, every page header | Wordmark renders as "SeenBy", single header on p.1 | Clipped "SeenI" and/or duplicated header block on cover |
| 5 | Monthly PDF p.4, AI Referral Traffic | Shows the latest entered month with honest sourcing | Says "Tracking begins soon — connecting your analytics" while June data (1,680) exists |
| 6 | Reports page: click Generate Report **with the Celery worker stopped**, wait 90s | UI surfaces a failure state | Silently returns to "No reports yet" with no error — then restart worker and confirm generation succeeds |
| 7 | Admin Competitors page → "Sources AI trusts in your category" | Section shows real source data | Shows "No source data yet. Run a scan" (Share-of-Source is empty on the demo client — backfill or re-scan before pitching) |
| 8 | Content Roadmap page | Copy matches the number of cards shown | Says "12 weekly content pieces" but renders only Weeks 1–3 |
| 9 | `/clients` overview | No test data visible | "ZZ Test Prospect DELETE" rows present, or cards stuck in "Scanning…" |

For PDF checks (#3, #4, #5): generate the report via the Reports page, download it, and inspect with the pdf skill (`pdftotext` for text, page screenshots for layout).

## Reporting

End with a table: check # · pass/fail · screenshot path · one-line evidence. Any FAIL = the demo is not clean; list fixes in priority order (1–6 are client-meeting blockers, 7–9 are pitch hygiene). Do not fix anything unprompted — this skill is a detector, not a fixer.

When all 9 pass consistently, update walkthrough.md §6.1 and the `seenby-handoff-2026-07` memory to reflect the fixes.
