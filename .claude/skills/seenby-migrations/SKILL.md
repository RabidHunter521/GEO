---
name: seenby-migrations
description: Alembic migration runbook for SeenBy — creating, verifying, and shipping schema changes safely. Trigger whenever a task adds/changes a SQLAlchemy model, mentions "migration", "alembic", "schema change", "new table/column", or before deploying schema changes to Supabase. Two real bugs (duplicate revision ID, unregistered test model) came from skipping these steps.
---

# SeenBy Migration Runbook

Postgres via Supabase in prod, SQLite-backed test bootstrap locally. Every schema change = model change + Alembic migration, always both, never raw ALTER TABLE.

## Creating a migration

1. **Model first**: one model file per domain entity in `backend/app/models/`. Follow an existing model for uuid PKs, timestamps, FK style.
2. **Register the model in the test bootstrap** (known trap: table silently missing in tests). Check how existing models are imported for metadata creation in `backend/tests/` conftest/bootstrap and add the new one.
3. **Write the migration by hand or autogenerate, then EDIT it**. Verify:
   - `down_revision` points at the current single head (`alembic heads` — run it, don't assume).
   - **Revision ID is unique** — grep it: `grep -r "<revision_id>" backend/alembic/versions/`. A duplicate revision ID (a1b2c3d4e5f6) has already collided once in this repo because hand-written IDs were copy-pasted. Prefer letting alembic generate the ID.
   - Descriptive filename: `<rev>_<snake_case_description>.py`.
4. **RLS**: every new client-data table enables row-level security inline in the same migration (see `e8f9a0b1c2d3_create_share_of_source_snapshots_table.py` for the pattern). No table with client data ships without RLS.
5. **Downgrade** must actually reverse the upgrade (drop policies before table).

## Verification (all must pass before commit)

```bash
cd backend && poetry run alembic heads          # exactly ONE head
cd backend && poetry run alembic history | head -30   # chain is linear, new rev on top
grep -rn "revision =" backend/alembic/versions/ | sort | uniq -d -f1   # no duplicate IDs
cd backend && poetry run pytest -q              # test bootstrap creates the table
```

## Known traps (each has bitten this repo)

- **Duplicate revision IDs** — collision breaks `alembic upgrade` for everyone. Always grep before commit.
- **Model not registered in test bootstrap** — tests pass without the table until something queries it.
- **Local ≠ Supabase**: a migration that ran on local SQLite/Postgres is NOT verified for prod. Say so explicitly in your report. Prod migration runs via the `seenby-release` skill runbook — never ad hoc.
- **Enum changes** on Postgres need explicit `ALTER TYPE`; autogenerate misses them.
- Multiple heads after a merge/rebase → `alembic merge` is a last resort; prefer re-parenting your new migration onto the true head.

## Report format

State: revision ID, parent revision, table/columns touched, RLS yes/no, verification command outputs (heads=1, tests pass), and whether prod (Supabase) has been migrated or still needs it.
