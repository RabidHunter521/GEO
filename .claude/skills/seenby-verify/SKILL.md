---
name: seenby-verify
description: Definition-of-done gate for SeenBy. Run before claiming any change is complete, before committing, and before merging. Runs backend tests, frontend typecheck/build, banned-language scan, and migration sanity checks. Trigger on "verify", "is this done", "ready to commit/merge", or after any feature/bugfix work.
---

# SeenBy Verification Gate

Run ALL applicable steps. Do not claim work is done until each relevant step passes with real output. If a step fails, fix it or report the failure verbatim — never skip silently.

## 1. Backend tests (if any Python touched)

```bash
cd backend && poetry run pytest -q
```

Fallback if poetry is unavailable: `cd backend && python -m pytest -q`.
All tests must pass. New behavior needs a new test — check that one was added.

## 1b. Backend lint (if any Python touched)

```bash
cd backend && poetry run ruff check app workers tests
```

Fallback if poetry/ruff is unavailable locally: `uvx ruff check app workers tests` from `backend/`.
Must report "All checks passed!" — this is what catches unused imports and dead code before they ship (see `pyproject.toml` `[tool.ruff.lint]` for the enabled rule set and the PERF203 exception).

## 2. Frontend typecheck + build (if any frontend touched)

```bash
cd frontend && npm run typecheck && npm run build
```

## 3. Banned-language scan (ALWAYS, if any client-facing text touched)

Client-facing surfaces = `frontend/src`, `backend/app/prompts`, email templates, report/PDF templates, `/view/*` pages. The language rules in CLAUDE.md §2 are non-negotiable. This regression has shipped twice before — check every time.

```bash
grep -rniE "\b(cited|uncited|citation rate|ranking position|visibility gap|first mentioned)\b" frontend/src backend/app/prompts backend/app/assets 2>/dev/null
grep -rniE "\b(confidence score|char offset|token count)\b" frontend/src 2>/dev/null
```

Expected result: **no matches in client-facing strings**. Matches inside internal admin-only code comments or variable names are acceptable; matches in JSX text, email copy, PDF templates, or Claude prompt output instructions are bugs.

## 4. Migration sanity (if any model/schema touched)

```bash
cd backend && poetry run alembic heads
```

- Exactly one head.
- Every schema change has an Alembic migration — no raw ALTER TABLE, no model change without migration.

## 5. Invariant checklist (read, confirm each)

- [ ] Score weights unchanged — or CLAUDE.md §4 updated AND `SCORE_VERSION` bumped.
- [ ] No hardcoded score band numbers — bands come from `constants.py` / `score-utils.ts`.
- [ ] `/view/[token]` responses still whitelist-only — no new internal fields (confidence, offsets, raw responses) exposed.
- [ ] No fetch calls in components — everything through `src/lib/api.ts`.
- [ ] Business logic in `app/services/`, not in routes or Celery tasks.
- [ ] Nothing from CLAUDE.md §11 (MVP exclusions) was built without explicit confirmation from Faris.

## 6. Report

State plainly what passed and what failed, with the actual command output for failures. "Tests pass" without having run them is a lie — do not do it.
