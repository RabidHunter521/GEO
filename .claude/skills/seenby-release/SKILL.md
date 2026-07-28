---
name: seenby-release
description: Production deploy runbook for SeenBy — pre-flight checks, Alembic migration against the real Supabase Postgres, env var diff, and post-deploy smoke test. Trigger on "deploy", "release", "push to prod", "run the migration on Supabase", or any production database change.
---

# SeenBy Release Runbook

Prod DB is **Supabase Postgres**. The #1 historical failure mode of this project is "migration ran locally, assumed done in prod" — this runbook exists to make that impossible. Never claim a release step is done without the command output.

## 1. Pre-flight (local)

- [ ] On master, working tree clean (demo/marketing files in root may stay untracked — do not delete them).
- [ ] `seenby-verify` skill passes end to end (tests, typecheck+build, banned-language grep, single alembic head).
- [ ] Note the release commit: `git rev-parse --short HEAD`.

## 2. Env var diff

Compare prod environment against `backend/.env.example`. Every key must exist in prod:

`DATABASE_URL, REDIS_URL, GEMINI_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY, RESEND_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ADMIN_API_KEY, ALLOWED_ORIGINS, FRONTEND_BASE_URL, CLOUDFLARE_R2_ENDPOINT_URL, CLOUDFLARE_R2_ACCESS_KEY_ID, CLOUDFLARE_R2_SECRET_ACCESS_KEY, CLOUDFLARE_R2_BUCKET_NAME, CLOUDFLARE_R2_PUBLIC_BUCKET_NAME, CLOUDFLARE_R2_PUBLIC_URL`

If a new env var was added this release, it goes to prod BEFORE the code deploy. Frontend needs its NextAuth + API base env vars checked on its host too.

## 3. Database migration (the critical step)

```bash
cd backend
# point at prod for THIS SHELL ONLY — never write the prod URL into any file
export DATABASE_URL="<supabase-connection-string>"   # from Supabase dashboard or Faris
poetry run alembic current      # record the starting revision
poetry run alembic upgrade head
poetry run alembic current      # must now equal `alembic heads`
```

Rules:
- Supabase: use the **direct connection string (port 5432)**, not the pooled one (6543) — DDL through pgbouncer transaction pooling can misbehave.
- Take a backup first: Supabase dashboard → Database → Backups (or `pg_dump`) — confirm one exists dated today before running upgrade.
- Verify the schema landed, e.g. for provenance: `SELECT COUNT(*) FROM scan_query_sources;` should return 0+ (table exists), not an error.
- Rollback: `poetry run alembic downgrade -1` — but prefer forward fixes; downgrades on prod data are last resort.
- `unset DATABASE_URL` (or close the shell) when done.

## 4. Deploy the apps

> **KNOWN GAP:** the actual hosting targets are not documented in the repo (backend has a Dockerfile; frontend is Next.js). Ask Faris where prod runs and then REPLACE this section with the real commands. Do not guess a deploy target.

Deploy backend (API + Celery worker + beat — all three must restart on the new code), then frontend.

## 5. Post-deploy smoke test (~10 min)

1. **Health**: hit the API root/health endpoint; load the admin login page.
2. **Auth**: log in; `/clients` renders with real data.
3. **Scan**: trigger a scan on a **prospect or low-stakes client** (never a paying client's the day before their report). Confirm: scan completes, score computed, activity log entry written.
4. **Provenance** (until first verified live): after the scan, `SELECT COUNT(*) FROM scan_query_sources WHERE scan_id = <new scan id>;` — Perplexity queries should produce rows. Then check the Competitors page "Sources AI trusts" section renders. Once this passes on prod for the first time, update the `seenby-citation-provenance` memory: it is verified.
5. **Client view**: open a share link — loads, no internal fields visible.
6. **PDF path**: generate a scorecard PDF (exercises WeasyPrint + R2 signing).
7. Check worker logs for errors; check no alert emails fired spuriously.

## 6. Record

Note in the activity/commit log: release commit, migration revisions (from → to), smoke test results, anything skipped. If anything was NOT verified, say so explicitly rather than implying a full pass.
