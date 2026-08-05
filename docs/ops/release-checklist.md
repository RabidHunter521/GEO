# Release Checklist

Deploy **mechanics** live in the `seenby-release` skill
(`.claude/skills/seenby-release/SKILL.md`) — pre-flight checks, the Alembic run
against Supabase, env-var diff, and the post-deploy smoke test. This file is
the per-phase **gate**: what must be true before that runbook is started.

> This checklist was created during Phase 6. The plan assumed it already
> existed; it did not, and `docs/ops/` did not either.

---

## Every release

- [ ] `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q` — all green
- [ ] `cd backend && .venv/Scripts/python.exe -m ruff check app workers tests`
- [ ] `cd frontend && npx vitest run --project unit`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm run build` (never while the dev server holds :3000)
- [ ] `git diff --check` — no whitespace errors
- [ ] CI green, including the `migrations` job (real Postgres upgrade,
      `downgrade base`, re-upgrade) and the "every table has RLS" job
- [ ] Banned-vocabulary scan clean (CLAUDE.md §2)
- [ ] Any new client-facing string reviewed against CLAUDE.md §2

## When the release changes the schema

- [ ] Single Alembic head
- [ ] Migration verified statically (`test_*_migration.py`) — a local
      `alembic upgrade` is **not** acceptable: `backend/.env` points at
      production Supabase
- [ ] Downgrade is symmetric and drops tables in FK-safe order
- [ ] Every new table does `ENABLE ROW LEVEL SECURITY` and `REVOKE ALL … FROM anon`
- [ ] No `GRANT` to any role
- [ ] Rollback target recorded in the phase's runbook

## Outstanding production migrations

Prod schema is **behind** the repo. These have never been applied:

| Revision | Phase |
|---|---|
| `c0f6b4e3d9a1` | 4 — industry packs |
| `d1a7c5f4e0b2` | 5 — tracked queries + sample metadata |
| `e2b8d6f5a1c3` | 5 — search signals |
| `f3c9e7a2b4d5` | 5 — conversion events |
| `a4b5c6d7e8f9` | 5 — merge |
| `e2b8d6a5f1c3` | 6 — benchmark data moat |

Run them in order via `seenby-release`. Do not cherry-pick.

---

## Phase 6 — Benchmark and Data Moat

Full detail in [benchmark-privacy-runbook.md](benchmark-privacy-runbook.md) §9.

- [ ] Privacy attack checks: cross-tenant denial on all four benchmark tables
      with a non-owner and an anonymous role
- [ ] Suppression verified: a below-threshold cohort returns a reason and no
      aggregate values anywhere in the response
- [ ] Member counts are banded, never exact, on every client-facing surface
- [ ] `benchmark_cohort_memberships` unreachable from any client or public schema
- [ ] Approved-snapshot immutability: update and delete both rejected
- [ ] Snapshot generation is idempotent across an interrupted rerun
- [ ] Publication: approval by a second actor, publish-does-not-recalculate,
      withdrawal closes public access without deleting the record
- [ ] `EXPLAIN (ANALYZE, BUFFERS)` on cohort eligibility, snapshot lookup and
      client comparison — confirm the Phase 6 indexes are used
- [ ] Three-pack acceptance walkthrough (healthcare, F&B, local services)
- [ ] **Accessibility walkthrough** — keyboard and 360px on `/benchmarks` and
      the client benchmark card. There is no automated coverage for these; the
      repo has no DOM test environment, so this manual pass is the only thing
      standing behind them.

### Known gap carried into this release

The banned-vocabulary CI job greps `frontend/src` for "citation rate" and
excludes only `//`-comment lines. It matches
`src/lib/__tests__/activity-page-rendering.test.ts:23`, where the phrase is
fixture data asserting the term is *not* rendered. This is legitimate test data
and a CI-side fix (exclude `__tests__`), not a code change. Decide before
relying on that job as a gate.
