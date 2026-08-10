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

## 3. Database migration — NORMALLY AUTOMATIC, DO NOT RUN BY HAND

**`backend/bin/start-web.sh` runs `alembic upgrade head` on every boot of the
Railway `api` service.** So a push to master migrates prod by itself, before
the new API serves traffic. `docs/DEPLOYMENT.md` §1.1 says explicitly: do not
run migrations by hand.

The default action here is therefore **nothing** — push (step 4) and let `api`
migrate. What you owe this step is *verification*, not execution:

```bash
cd backend
# READ-ONLY. backend/.env already points at prod, so no export is needed.
./.venv/Scripts/alembic.exe current   # before: note the revision
# ... push, wait for the api service to redeploy ...
./.venv/Scripts/alembic.exe current   # after: must equal `alembic heads`
```

Before pushing, always check what the deploy will apply — `start-web.sh` runs
it unattended with no review gate:

```bash
./.venv/Scripts/alembic.exe upgrade <current_prod_rev>:head --sql   # offline, executes nothing
```

Read that SQL. If it contains anything destructive (DROP, ALTER ... TYPE, NOT
NULL on a populated column, data backfill), **stop** — it will run the moment
the new `api` boots. Confirm a same-day Supabase backup exists first.

Run `alembic upgrade head` manually ONLY when you deliberately want the schema
to land ahead of the code (rare — additive index/column that a later deploy
needs). If you do, say so in the release notes; the automatic run afterwards
is a harmless no-op once the revision is already stamped.

Rules:
- Supabase: **session pooler on port 5432**, not transaction pooling on 6543 — DDL through pgbouncer transaction pooling can misbehave. (The pooler *host* is correct and required; Railway can't reach the IPv6-only direct host. It's the port that matters.)
- Verify the schema actually landed — check `pg_indexes` / `information_schema`, don't trust the exit code.
- Rollback: `alembic downgrade -1` — but prefer forward fixes; downgrades on prod data are last resort.

## 4. Deploy the apps — automatic on push to master

**Railway, one project, 4 services + Redis.** Every service watches `master`
with "Deploy on push" enabled, so `git push origin master` redeploys all four.
There is no manual deploy command and no deploy step in CI (`ci.yml` only runs
tests). Full topology and env-var worksheet: **`docs/DEPLOYMENT.md`**.

| Service | Source | Start command | Public? |
|---|---|---|---|
| `api` | `backend/` | `bin/start-web.sh` (runs migrations first) | no — private network only |
| `worker` | `backend/` | `bin/start-worker.sh` | no |
| `beat` | `backend/` | `bin/start-beat.sh` | no |
| `frontend` | `frontend/` | Next.js standalone | **yes** — `app.seenby.my` |

```bash
git push origin master   # this alone deploys everything
```

The frontend reaches the API at `http://api.railway.internal:8000` over
Railway's private network — the API has no public hostname, so there is
nothing to curl from outside. Consequences worth knowing:

- All four services restart on every push, even a one-file change.
- **You cannot verify a deploy from outside.** Every admin route is behind
  auth, so an unauthenticated probe returns the same 307 → `/auth/login` on
  old and new code alike. To confirm a release actually landed, read the
  Railway deploy logs for each service, or log in and look for the change.
  Do not infer success from the site merely responding.

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
