# Phase 4 — Industry Intelligence Packs: Release Evidence

Plan: `docs/superpowers/plans/2026-07-29-seenby-industry-intelligence-packs.md`
Branch: `feat/industry-intelligence-packs` (base `bf07a2b`)
Date: 2026-08-04

## Automated verification (Task 10 Steps 1–2, 5)

| Gate | Result |
|---|---|
| Backend tests | **1387 passed** (baseline 1117 at `bf07a2b`, **+270**) |
| Backend lint (`ruff check app tests`) | All checks passed |
| Frontend typecheck (`tsc --noEmit`) | Clean |
| Frontend unit tests | 81 passed / 34 suites |
| Frontend `next build` | Clean at `ebe9961`; no frontend file changed after that commit |
| Alembic heads | Single head `c0f6b4e3d9a1` |
| Migration chain integrity | 6/6 passed (tracked-by-git, parents resolve, reaches base, no duplicate IDs) |
| `git diff --check` | Clean |

### Migration up/down/up (Step 1)

**Not run locally, deliberately.** `backend/.env` `DATABASE_URL` points at the
production Supabase instance (`aws-1-ap-northeast-2.pooler.supabase.com:5432`),
so running `alembic upgrade head` here would migrate production outside the
`seenby-release` runbook.

The exact cycle this step asks for already runs in CI against a throwaway
Postgres — `.github/workflows/ci.yml` performs `alembic upgrade head`,
`alembic current`, an RLS assertion, then `alembic downgrade base` and a
re-upgrade. That is a stronger check than a local run against SQLite, which
cannot execute these migrations at all.

**Production is NOT migrated.** `c0f6b4e3d9a1` must be applied via the
`seenby-release` runbook.

### Horizontal-core integrity (Step 5)

| Assertion | Evidence |
|---|---|
| No pack-specific table | `c0f6b4e3d9a1` contains only `add_column`/`drop_column` — no `create_table` |
| No forked API | No file under `backend/app/api/` references a pack key |
| No forked client portal | `frontend/src/app/view/[token]/` unchanged: same six routes as before Phase 4 |
| No new models | Only `client.py` modified (three nullable columns) |
| No approval/regulatory claims | All **155** pack-authored strings across all three packs swept for legal, licensing, certification and endorsement claims, plus the CLAUDE.md §2 banned vocabulary — **none found** |

The no-verdict rule is enforced structurally, not just by review:
`validate_pack` rejects any risk rule whose `review_instruction` contains a
legal or regulatory conclusion, at import time, for every pack.

## Outstanding — needs admin browser login (Task 10 Steps 3, 4, 6)

These require signing into the admin app, which the assistant does not do.
**Scope every step to the named throwaway clients below.** A previous phase's
live verification wrote three authority assets onto Medilink Healthcare, a real
client.

Create: `ZZ Pack Test HEALTHCARE`, `ZZ Pack Test FNB`, `ZZ Pack Test LOCAL`.

### Step 3 — one acceptance scenario per pack

For each of the three clients:

1. `/clients/[id]/settings` → **Industry pack** → select the pack. Confirm the
   subcategory dropdown populates with that pack's subcategories only, and that
   saving shows a "Pack version 1.0.0" badge.
2. Verify the API rejects a foreign subcategory: choosing an F&B subcategory
   under Healthcare should be impossible in the UI, and a direct PATCH with one
   must return 422.
3. `/clients/[id]/reputation/truth` → confirm the fact groups are now the
   PACK's (Practitioner / Treatment / Accreditation … for Healthcare), not the
   generic six.
4. Add one ordinary fact and one **risk-sensitive** fact (e.g. Healthcare
   → Qualification, F&B → Halal status, Local → Licences held). Confirm the
   risk-sensitive one will not save without a Source URL, and shows the
   "Needs a source" badge once created. Approve both.
5. Run a scan. Confirm the queries in `/clients/[id]/scan` are the pack's buyer
   questions (not the legacy "Tell me about X" set), that **no query contains a
   `{placeholder}`**, and that the count is ≤ 20.
6. Generate a content brief and a roadmap. Confirm the copy uses the industry's
   vocabulary and asserts nothing outside the approved facts.
7. Generate a report. Confirm the accuracy section carries the pack's label
   ("Practitioner and treatment facts reviewed" / "Outlet, menu and dietary
   information reviewed" / "Service-area, licensing and availability facts
   reviewed").

### Step 4 — pack-change safety

8. On one test client, change the pack. Confirm the dialog appears and states:
   facts kept, N fields carry over, which fact types stop/start being tracked,
   subcategory cleared, benchmarks reset.
9. **Cancel** it. Confirm nothing changed — pack, subcategory and version are
   all as before.
10. Change it again and confirm. Confirm the subcategory cleared, the version
    re-stamped to the NEW pack's version, and previously approved facts still
    exist (the page should show the "facts recorded outside this pack are kept"
    line).

### Step 6 — record

11. Archive/delete the three throwaway clients when finished.

## Known deviations from the plan

| Plan says | What shipped | Why |
|---|---|---|
| F&B backfill term `food` | Dropped; added `bakery`, `dentist`, `healthcare` | "Food Packaging" / "Pet Food Manufacturer" would be misclassified and word boundaries cannot help |
| Each pack task modifies `registry.py` | Packs self-register; `__init__.py` imports them | `registry.py` stays ignorant of individual packs |
| Modify `truth_comparison_service.py` | Not modified | The pack is only knowable at the persistence boundary; that service's severity default is the right no-pack fallback |
| Modify `LocationSelector.tsx` | Not modified | Locations are pack-independent; no pack-driven behaviour to add |
| Store pack provenance "with the finding metadata" | Namespaced into the existing `rule_key` column | Phase 4's migration contract is client-columns-only; the program index lists exactly one Phase 4 migration |
| Task 2 asserts "three keys" | Deferred to Task 5 | The three packs do not exist until Tasks 3–5 |
