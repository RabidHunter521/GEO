# SeenBy — Production Deployment Runbook

Localhost → live, ready for real clients. Work top to bottom. Fill in the
**worksheet** at the bottom as you provision each service, then paste those
values into Railway and Vercel.

> Architecture: everything that runs code lives on **Railway** (4 services, 2
> Docker images) in one project. DB on **Supabase**, files on **Cloudflare
> R2**, email via **Resend**, optional alerts via **Telegram**. The frontend
> talks to the API over Railway's **private network** — the API is never
> exposed publicly, so there is no `api.seenby.my`.

| Piece | Host | Source of truth |
|---|---|---|
| API + worker + beat | Railway (3 services, 1 image) | `backend/bin/start-*.sh`, `backend/Dockerfile` |
| Admin panel | Railway (1 service) | `frontend/Dockerfile` (Next.js 15 standalone) |
| PostgreSQL | Supabase (session pooler) | `backend/.env.example` |
| Redis (Celery broker) | Railway plugin | `REDIS_URL` in `app/core/config.py` |
| File storage | Cloudflare R2 (2 buckets) | `CLOUDFLARE_R2_*` |
| Email | Resend (sender `contact@seenby.my`) | `app/services/email_service.py` |
| Admin alerts | Telegram (optional) | `TELEGRAM_*` |

Accounts needed: Railway, Supabase, Cloudflare, Resend, billing-enabled API
keys for Anthropic / OpenAI / Gemini / Perplexity, and DNS control for
`seenby.my`.

Only the **frontend** service gets a public Railway domain. `api`, `worker`,
and `beat` should never have public networking enabled — Railway gives every
service in a project a private DNS name (`<service-name>.railway.internal`)
automatically, reachable only from other services in the same project.

---

## Phase 1 — Provision infrastructure & collect secrets

### 1.1 Supabase (database)
- New project, region `ap-southeast-1` (Singapore, closest to KL).
- Settings → Database → Connect → **Session pooler** → copy the `DATABASE_URL`.
  - ⚠️ Must be the **session pooler** (IPv4). The direct `[project].supabase.co`
    host is IPv6-only and will fail on Railway.
- Migrations run automatically on deploy (`alembic upgrade head` in
  `start-web.sh`) — do **not** run them by hand.
- ⚠️ Free tier **pauses on inactivity**, which silently breaks scheduled digests
  and reports. Use a paid tier before onboarding real clients.

### 1.2 Cloudflare R2 (two buckets)
- Bucket `seenby-reports` → **public access OFF**. (PDFs served only via
  short-lived presigned URLs.)
- Bucket `seenby-public` → **public access ON**, attach custom domain
  `cdn.seenby.my` (or use the r2.dev URL). Holds client logos embedded in emails.
- Create an R2 API token (Object Read & Write) → records:
  - `CLOUDFLARE_R2_ACCESS_KEY_ID`
  - `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
  - `CLOUDFLARE_R2_ENDPOINT_URL` = `https://<account_id>.r2.cloudflarestorage.com`

### 1.3 Resend (email) — gates ALL client delivery
- Add and **verify the `seenby.my` domain** (not just one address). Sender is
  hardcoded to `contact@seenby.my`; without domain verification every digest,
  report, and alert fails.
- Add the SPF + DKIM + DMARC DNS records Resend provides (see Phase 4).
- Copy `RESEND_API_KEY`.

### 1.4 LLM provider keys (with spend caps)
- Production keys: **Anthropic (required)**, OpenAI, Gemini, Perplexity.
- Set a hard billing limit on each provider dashboard as a backstop.
- App-level guardrails already exist (`BUDGET_CLIENT_MONTHLY_USD=20`,
  `BUDGET_GLOBAL_DAILY_USD=50` in `config.py`). Confirm these fit your pricing
  before the first real scan.

### 1.5 Generate your own secrets (Git Bash)
```bash
openssl rand -hex 32     # ADMIN_API_KEY  (shared frontend ↔ backend, must match)
openssl rand -hex 32     # AUTH_SECRET    (next-auth)
openssl rand -base64 24  # ADMIN_PASSWORD (your login)
```

### 1.6 Telegram alerts (optional, recommended for solo ops)
- @BotFather → new bot → `TELEGRAM_BOT_TOKEN`.
- Message the bot, then read `getUpdates` to find `TELEGRAM_CHAT_ID`.
- Leave both blank to disable — alerts still go to email.

---

## Phase 2 — Deploy to Railway (backend + frontend, one project)

One Railway project = **Redis + 4 services** — 3 from `backend/Dockerfile`,
1 from `frontend/Dockerfile`.

1. **Add Redis** (New → Database → Redis) → copy `REDIS_URL`.
2. **Service `api`** — source `backend/`, start command `bin/start-web.sh`
   (Dockerfile default). **Leave public networking off.**
3. **Service `worker`** — source `backend/`, start command
   `bin/start-worker.sh`. No networking needed at all.
4. **Service `beat`** — source `backend/`, start command `bin/start-beat.sh`.
   No networking needed at all.
5. **Service `frontend`** — source `frontend/` (uses `frontend/Dockerfile`).
   This is the only service that gets a public domain.

Set **the same backend env vars on `api`, `worker`, AND `beat`** (worker &
beat need DB/Redis/LLM/email keys too — see worksheet). Then:

- Deploy `api` **first** (it runs the migrations), then `worker`, then `beat`,
  then `frontend`.
- ⚠️ Set `RATE_LIMIT_TRUSTED_PROXY=1` on the backend services — Railway sits
  behind a proxy, so the rate limiter must trust `X-Forwarded-For`.
- On `frontend`, set `API_BASE_URL=http://api.railway.internal:8000` —
  Railway's private networking. It resolves `<service-name>.railway.internal`
  only within the same project (swap `api` for whatever you actually name the
  service). This means the FastAPI service is **never reachable from the
  public internet**, unlike the old Vercel+public-API setup.
- Generate a public domain for `frontend` only → `app.seenby.my` (or the
  railway.app URL), via Settings → Networking → Public Networking.
- Security: the browser never sees `ADMIN_API_KEY` — `src/lib/api.ts` is
  server-only and calls the backend over the private network. Keep it that
  way.

After the domain resolves, confirm the backend's `ALLOWED_ORIGINS` and
`FRONTEND_BASE_URL` exactly match `https://app.seenby.my` (HTTPS, no trailing
slash). HSTS is already set in `next.config.ts` and activates over TLS.

---

## Phase 3 — DNS (one pass at the registrar)

| Record | Type | Points to | For |
|---|---|---|---|
| `app.seenby.my` | CNAME | Railway `frontend` service | admin panel |
| `cdn.seenby.my` | CNAME | R2 public bucket | client logos |
| `seenby.my` SPF | TXT | Resend value | email auth |
| Resend DKIM | CNAME/TXT | Resend values | email auth |
| `_dmarc.seenby.my` | TXT | Resend value | email auth |

No `api.seenby.my` record — the API is private-network-only (Phase 2).

---

## Phase 4 — Go-live smoke test (on a throwaway test client, before any real client)

- [ ] Log into `app.seenby.my` with admin credentials
- [ ] Create a test client → run a **scan** → all enabled platforms return
      (check activity log; "unavailable" platform = bad/missing key)
- [ ] Generate **AI Readiness Toolkit** files → run verification crawler
- [ ] Generate a **monthly PDF report** → lands in `seenby-reports` bucket,
      opens via presigned link
- [ ] Open the **public client view** `/view/[token]` in incognito → renders;
      an invalid token returns 404
- [ ] Trigger a **weekly digest** → email arrives (check spam = DKIM/DMARC not
      fully propagated yet)
- [ ] Force an alert condition → email + Telegram fire
- [ ] Confirm a scan over `BUDGET_*` is hard-blocked (validates guardrails)

---

## Phase 5 — Operational readiness

- **Backups:** confirm Supabase plan retains backups and doesn't pause.
- **Uptime:** add a monitor (e.g. UptimeRobot) on `app.seenby.my`. The API has
  no public URL to monitor directly — set a Railway health check path
  (`/health`) on the `api` service (Settings → Healthcheck) and watch its
  deploy logs instead.
- **Cron health:** digests, reports, and the daily retention/purge job run from
  the `beat` service — keep it running and watch its logs.
- **Cost ceiling:** provider billing caps + in-app budgets = belt & suspenders.
- **Retention:** 90-day raw scan responses + 6-month churn deletion run via the
  beat maintenance task.

---

## Env-var worksheet

Fill these in as you provision. `ADMIN_API_KEY` must be **identical** on backend
and frontend.

### Backend (Railway — set on `api`, `worker`, AND `beat`)

| Var | Value | From |
|---|---|---|
| `DATABASE_URL` | | Supabase session pooler (1.1) |
| `REDIS_URL` | | Railway Redis (2.1) |
| `ANTHROPIC_API_KEY` | | Anthropic (1.4) — required |
| `OPENAI_API_KEY` | | OpenAI (1.4) |
| `GEMINI_API_KEY` | | Google (1.4) |
| `PERPLEXITY_API_KEY` | | Perplexity (1.4) |
| `RESEND_API_KEY` | | Resend (1.3) |
| `ADMIN_API_KEY` | | generated (1.5) — shared |
| `ALLOWED_ORIGINS` | `https://app.seenby.my` | Phase 2 |
| `FRONTEND_BASE_URL` | `https://app.seenby.my` | Phase 2 |
| `CLOUDFLARE_R2_ENDPOINT_URL` | | R2 (1.2) |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | | R2 (1.2) |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | | R2 (1.2) |
| `CLOUDFLARE_R2_BUCKET_NAME` | `seenby-reports` | R2 (1.2) |
| `CLOUDFLARE_R2_PUBLIC_BUCKET_NAME` | `seenby-public` | R2 (1.2) |
| `CLOUDFLARE_R2_PUBLIC_URL` | `https://cdn.seenby.my` | R2 (1.2) |
| `RATE_LIMIT_TRUSTED_PROXY` | `1` | required on Railway |
| `BUDGET_CLIENT_MONTHLY_USD` | `20` (default) | confirm vs pricing |
| `BUDGET_GLOBAL_DAILY_USD` | `50` (default) | confirm vs pricing |
| `TELEGRAM_BOT_TOKEN` | (optional) | Telegram (1.6) |
| `TELEGRAM_CHAT_ID` | (optional) | Telegram (1.6) |

### Frontend (Railway — set on `frontend`)

| Var | Value | From |
|---|---|---|
| `NEXTAUTH_URL` | `https://app.seenby.my` | Phase 2 |
| `AUTH_SECRET` | | generated (1.5) |
| `ADMIN_USERNAME` | | your choice |
| `ADMIN_PASSWORD` | | generated (1.5) |
| `API_BASE_URL` | `http://api.railway.internal:8000` | Railway private network (Phase 2) — not a public URL |
| `ADMIN_API_KEY` | | **same as backend** (1.5) |

---

## Decisions to confirm before launch

1. **Domain split** — this runbook assumes only `app.` (admin, public) and
   `cdn.` (logos, public) are real DNS records; `api` is private-network-only
   and never gets a hostname. Apex `seenby.my` is free for a future marketing
   site.
2. **Paid tiers** — free Supabase/Railway tiers pause and break cron jobs. Real
   clients require paid tiers (~$5–20/mo each to start).
3. **Budget caps** — `$20/client/month`, `$50/day global` are the shipped
   defaults. Confirm they match your unit economics.

**Is the app fully ready after the deployment guide?**
Yes, functionally. The one thing the guide doesn't cover is production
hardening over time — but for a solo operator with real clients it's
complete: code runs, emails send, scans execute, PDFs generate, client view
works. Cost guardrails, circuit breakers, and alerts are already built in.
Backups, uptime monitoring, and cron health are your only ongoing ops tasks.

**Will a GitHub push auto-deploy everywhere?**
Yes — enable it once per service during setup. When you create each service
(`api`, `worker`, `beat`, `frontend`), Railway asks which branch to watch —
pick `master` and tick "Deploy on push." After that, every push redeploys all
four.

```
git push → GitHub → webhook → Railway redeploys api      (runs alembic upgrade head first)
                             → Railway redeploys worker
                             → Railway redeploys beat
                             → Railway redeploys frontend
```

Two things to be careful about:
- Migrations run on every `api` restart (`alembic upgrade head` in
  `start-web.sh`). That's safe if migrations are additive. If you ever push a
  destructive migration, it runs the moment the new `api` service boots — no
  review gate. For now that's fine; just be aware.
- All four Railway services redeploy on every push, even if you only changed
  one file. That means a brief worker restart on every deploy. Not a problem
  for on-demand scans, but worth knowing.

The practical flow once live:

```bash
git add .
git commit -m "feat: ..."
git push origin master   # this alone deploys everything
```

One push, everything updates — the full CI/CD pipeline, one platform, no
extra tooling needed for MVP.