# SeenBy — Production Deployment Runbook

Localhost → live, ready for real clients. Work top to bottom. Fill in the
**worksheet** at the bottom as you provision each service, then paste those
values into Railway and Vercel.

> Architecture is already baked into the repo — don't second-guess the stack:
> backend on **Railway** (3 services, 1 Docker image), DB on **Supabase**,
> Redis on **Railway**, frontend on **Vercel**, files on **Cloudflare R2**,
> email via **Resend**, optional alerts via **Telegram**.

| Piece | Host | Source of truth |
|---|---|---|
| API + worker + beat | Railway (3 services) | `backend/bin/start-*.sh`, `backend/Dockerfile` |
| PostgreSQL | Supabase (session pooler) | `backend/.env.example` |
| Redis (Celery broker) | Railway plugin | `REDIS_URL` in `app/core/config.py` |
| Admin panel | Vercel | `frontend/` (Next.js 15 SSR) |
| File storage | Cloudflare R2 (2 buckets) | `CLOUDFLARE_R2_*` |
| Email | Resend (sender `contact@seenby.my`) | `app/services/email_service.py` |
| Admin alerts | Telegram (optional) | `TELEGRAM_*` |

Accounts needed: Railway, Vercel, Supabase, Cloudflare, Resend, billing-enabled
API keys for Anthropic / OpenAI / Gemini / Perplexity, and DNS control for
`seenby.my`.

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

## Phase 2 — Deploy backend on Railway

One Railway project = **Redis + 3 services**, all pointing at `backend/` and the
same `Dockerfile`.

1. **Add Redis** (New → Database → Redis) → copy `REDIS_URL`.
2. **Service `api`** — start command `bin/start-web.sh` (Dockerfile default).
3. **Service `worker`** — start command `bin/start-worker.sh`.
4. **Service `beat`** — start command `bin/start-beat.sh`.

Set **the same env vars on all three** (worker & beat need DB/Redis/LLM/email
keys too — see worksheet). Then:

- Deploy `api` **first** (it runs the migrations), then `worker`, then `beat`.
- Generate a public domain for `api` → `api.seenby.my` (or use the railway.app
  URL). Copy it for Phase 3.
- ⚠️ Set `RATE_LIMIT_TRUSTED_PROXY=1` — Railway sits behind a proxy, so the
  rate limiter must trust `X-Forwarded-For`.

---

## Phase 3 — Deploy frontend on Vercel

1. Import repo → **Root Directory = `frontend`** (auto-detects Next.js).
2. Set env vars (see worksheet). Key ones:
   - `API_BASE_URL` = the Railway `api` URL
   - `ADMIN_API_KEY` = **exactly** the same value as on the backend
   - `NEXTAUTH_URL` = `https://app.seenby.my`
3. Deploy, then add custom domain `app.seenby.my` (add the CNAME at registrar).
4. Security: the browser never sees `ADMIN_API_KEY` — `src/lib/api.ts` is
   server-only and calls Railway server-to-server. Keep it that way.

After the domain resolves, confirm Railway's `ALLOWED_ORIGINS` and
`FRONTEND_BASE_URL` exactly match `https://app.seenby.my` (HTTPS, no trailing
slash). HSTS is already set in `next.config.ts` and activates over TLS.

---

## Phase 4 — DNS (one pass at the registrar)

| Record | Type | Points to | For |
|---|---|---|---|
| `app.seenby.my` | CNAME | Vercel | admin panel |
| `api.seenby.my` | CNAME | Railway api service | backend |
| `cdn.seenby.my` | CNAME | R2 public bucket | client logos |
| `seenby.my` SPF | TXT | Resend value | email auth |
| Resend DKIM | CNAME/TXT | Resend values | email auth |
| `_dmarc.seenby.my` | TXT | Resend value | email auth |

---

## Phase 5 — Go-live smoke test (on a throwaway test client, before any real client)

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

## Phase 6 — Operational readiness

- **Backups:** confirm Supabase plan retains backups and doesn't pause.
- **Uptime:** add a monitor (e.g. UptimeRobot) on `api.seenby.my/health` (or
  `/docs`) and `app.seenby.my`.
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
| `ALLOWED_ORIGINS` | `https://app.seenby.my` | Phase 3 |
| `FRONTEND_BASE_URL` | `https://app.seenby.my` | Phase 3 |
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

### Frontend (Vercel)

| Var | Value | From |
|---|---|---|
| `NEXTAUTH_URL` | `https://app.seenby.my` | Phase 3 |
| `AUTH_SECRET` | | generated (1.5) |
| `ADMIN_USERNAME` | | your choice |
| `ADMIN_PASSWORD` | | generated (1.5) |
| `API_BASE_URL` | `https://api.seenby.my` | Railway api (Phase 2) |
| `ADMIN_API_KEY` | | **same as backend** (1.5) |

---

## Decisions to confirm before launch

1. **Domain split** — this runbook assumes `app.` (admin) + `api.` (backend) +
   `cdn.` (logos), leaving apex `seenby.my` for a future marketing site. Adjust
   if you'd rather run the app on the apex.
2. **Paid tiers** — free Supabase/Railway tiers pause and break cron jobs. Real
   clients require paid tiers (~$5–20/mo each to start).
3. **Budget caps** — `$20/client/month`, `$50/day global` are the shipped
   defaults. Confirm they match your unit economics.
