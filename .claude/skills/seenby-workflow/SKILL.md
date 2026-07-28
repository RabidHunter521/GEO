---
name: seenby-workflow
description: How to execute any feature or bugfix in the SeenBy codebase — sequencing, scope discipline, and where things live. Trigger at the START of any coding task in this repo (add feature, fix bug, refactor), before writing code.
---

# SeenBy Change Workflow

Follow this sequence for every change. It exists because skipping steps is how demo bugs and language-rule leaks shipped before.

## 0. Orient (2 minutes, no code)

1. Re-read CLAUDE.md §2 (language rules), §4 (score dimensions), §11 (MVP exclusions).
2. If the request touches anything in §11 (client login, billing, scheduled scans, webhooks…): **stop and confirm with Faris first.**
3. State your plan in 2–4 sentences before editing: what files, what test proves it works, what could break.

## 1. Branch

Never work directly on master for multi-file changes. `git checkout -b feat/<slug>` or `fix/<slug>`.

## 2. Locate the right layer

| Change type | Where it goes |
|---|---|
| API behavior | `backend/app/api/v1/` (thin) → logic in `backend/app/services/` |
| Constants / bands / weights | `backend/app/core/constants.py` + `frontend/src/lib/score-utils.ts` |
| Schema change | model file + Alembic migration (always both) |
| Background work | `backend/workers/tasks/` (thin entrypoint → service) |
| UI | `frontend/src/`, shadcn/ui only, API calls via `src/lib/api.ts`, types in `src/types/index.ts` |
| Client-facing words | must pass CLAUDE.md §2 table — "Seen by AI", never "cited/mentioned" |

## 3. Test first, then implement

Write or extend a test in `backend/tests/` that fails for the right reason, then make it pass. The scan engine, alerting, and provenance subsystems all have existing test files — extend the matching one rather than creating parallel files.

Known trap: tests that touch the scan flow must mock enrichment (`enrich_scan_sources`) and external APIs, or they make live network calls and flake. See `test_api_provenance.py` / conftest patterns.

## 4. Keep the diff surgical

Fix what was asked. Do not reformat neighboring code, rename things opportunistically, or "improve" unrelated files. If you notice adjacent problems, list them in your final report instead of fixing them inline.

## 5. Verify

Invoke the `seenby-verify` skill. All gates must pass before you say "done".

## 6. Report honestly

Lead with what changed and the verification evidence. If anything was skipped or is unverified (e.g., needs a live scan or real Postgres), say so explicitly — unverified-but-probably-fine has bitten this project before (migration ran locally, never against Supabase).
