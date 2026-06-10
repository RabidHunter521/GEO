# Pending — Faris Action Required

## 1. Credentials (backend/.env)

| Variable | Current State | What to do |
|---|---|---|
| `ANTHROPIC_API_KEY` | `placeholder` | Get from console.anthropic.com — needed for toolkit generation + weekly digest |
| `RESEND_API_KEY` | `placeholder_resend_key` | Get from resend.com dashboard — needed for digest + report emails |
| `ADMIN_JWT_SECRET` | weak placeholder | Replace with a real 32+ char random string |
| `CLOUDFLARE_R2_ENDPOINT_URL` | missing | Set after creating R2 bucket |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | missing | Set after creating R2 bucket |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | missing | Set after creating R2 bucket |
| `CLOUDFLARE_R2_BUCKET_NAME` | missing (defaults to `seenby-reports`) | Only needed if you name the bucket differently |
| `CLOUDFLARE_R2_PUBLIC_URL` | missing | Public URL prefix for R2 objects — used in report download links |

## 2. Credentials (frontend/.env.local)

| Variable | Current State | What to do |
|---|---|---|
| `ADMIN_PASSWORD` | `admin123` | Change to something strong before going live |
| `AUTH_SECRET` | dev placeholder | Replace with a real random secret |

## 3. Infrastructure

- [ ] **Cloudflare R2** — Create bucket `seenby-reports`, enable public access (or custom domain), copy endpoint + access key + secret into `backend/.env`
- [ ] **Resend** — Verify the `seenby.my` domain so `contact@seenby.my` is a valid sender. Without this all digest and report emails fail.
- [ ] **Redis** — Currently `redis://localhost:6379/0`. If deploying outside local machine, set a hosted Redis URL (Upstash, Railway, etc.) before Celery workers and the weekly beat scheduler will run.

## 4. Database Migrations

Run this after every deployment / new migration:

```bash
cd backend
alembic upgrade head
```

Two migrations exist that may not have been applied yet: `add_toolkit_files_table` and `create_reports_table`.

## 5. Ongoing Manual Responsibilities (by design — MVP spec)

- **Brand Authority Score** and **Content Quality Score** — assess per client and enter via client settings. These never auto-compute. Shows "Assessed by SeenBy team" label in the UI.
- **Monthly PDF review** — system auto-generates it on schedule, but you manually click "Send to Client" after reviewing.
- **`score_drop_threshold`** — defaults to 35 per client. Adjust per-client in settings if needed.
- **Alert emails** go to `contact@seenby.my` — monitor that inbox. No in-app alert panel in MVP.
