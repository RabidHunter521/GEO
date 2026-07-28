# VPS Deployment Guide

Single-VPS deploy via Docker Compose. Postgres stays on Supabase, files stay
on Cloudflare R2 — this VPS only runs compute: frontend, backend API,
Celery worker, Celery beat, Redis, and Caddy (reverse proxy + auto TLS).

Repo files this relies on: `docker-compose.yml`, `Caddyfile`,
`backend/.env.production.example`, `frontend/.env.production.example`,
`frontend/Dockerfile`, `backend/Dockerfile`.

## 1. Provision the server

Pick one (both are Ubuntu 24.04 LTS, both work identically for this guide):

- **Hetzner CX22** (~€4.5/mo, 2 vCPU / 4GB RAM) — best price/performance. [hetzner.com/cloud](https://www.hetzner.com/cloud)
- **DigitalOcean Basic Droplet** ($6–12/mo) — if you want their web UI / monitoring.

When creating it:
- Ubuntu 24.04 LTS
- Add your SSH public key during creation (don't use password auth)
- Note the server's public IP

You do this step yourself — it's account creation + payment, which I can't do on your behalf.

## 2. DNS

Point your domain at the server before you need TLS:
- `A` record: `your-domain.com` → server IP
- Optionally `A` record: `www.your-domain.com` → server IP

DNS propagation can take a few minutes to a few hours — do this first so it's ready by the time you need Caddy to issue a cert.

## 3. Harden the server (SSH in as root)

```bash
ssh root@<server-ip>

# Create a non-root user with sudo
adduser deploy
usermod -aG sudo deploy

# Copy your SSH key to the new user
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

# Firewall: only SSH, HTTP, HTTPS
apt update && apt install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Optional but recommended: fail2ban against SSH brute-force
apt install -y fail2ban
```

From here on, SSH in as `deploy`, not `root`:

```bash
ssh deploy@<server-ip>
```

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy
# log out and back in for the group change to apply
exit
ssh deploy@<server-ip>
docker --version
docker compose version
```

## 5. Get the code onto the server

```bash
sudo apt install -y git
git clone https://github.com/<your-org>/<your-repo>.git seenby
cd seenby
git checkout master   # or whichever branch is your deploy branch
```

## 6. Real env files (never committed)

```bash
cp backend/.env.production.example backend/.env.production
cp frontend/.env.production.example frontend/.env.production
nano backend/.env.production    # fill in real DATABASE_URL, API keys, R2 creds
nano frontend/.env.production   # fill in real AUTH_SECRET, ADMIN_PASSWORD, etc.
```

Pull the real values from wherever you currently keep them (password manager,
existing `.env` files, Supabase/Cloudflare dashboards). The full key list is
in the `seenby-release` skill.

`ADMIN_API_KEY` must be identical in both files — it's how the frontend
authenticates its server-side calls to the backend.

## 7. Point the Caddyfile at your real domain

```bash
nano Caddyfile
```

Replace `your-domain.com` with your actual domain.

## 8. First boot

```bash
docker compose up -d --build
docker compose ps        # all 6 services should show "running" / "healthy"
docker compose logs -f backend-web   # watch migrations run, confirm no errors
```

`backend-web`'s startup script runs `alembic upgrade head` automatically —
watch this log on first boot especially, since it's live against your
Supabase database. If it fails, **do not** proceed; fix the migration issue
first (see the `seenby-release` skill's migration section for the general
runbook — same rules apply here, just triggered by container start instead
of a manual `alembic upgrade head`).

Caddy will attempt to issue a Let's Encrypt cert for your domain on first
request — this only works once DNS has actually propagated to this server's
IP.

## 9. Smoke test

Same checklist as the `seenby-release` skill's post-deploy section:
1. `https://your-domain.com` loads, login page renders
2. Log in, `/clients` renders with real data
3. Trigger a scan on a low-stakes client, confirm it completes
4. Open a `/view/<token>` share link, confirm it loads with no internal fields
5. Generate a scorecard PDF (exercises WeasyPrint + R2)
6. `docker compose logs backend-worker backend-beat` — no errors

## 10. Ongoing deploys

```bash
cd seenby
git pull
docker compose up -d --build
```

This rebuilds only the images whose source changed and restarts those
containers; Redis and Caddy's TLS state (in their named volumes) persist
across deploys.

## 11. Day-to-day operations

```bash
docker compose logs -f              # all services, tailed
docker compose logs -f backend-worker
docker compose ps
docker compose restart backend-web  # restart one service
docker compose down                 # stop everything (volumes persist)
```

Backups: your data lives in Supabase (has its own backup schedule — confirm
it in the Supabase dashboard) and Cloudflare R2. The VPS itself is stateless
compute; if it dies, a fresh server + `git clone` + real `.env.production`
files + `docker compose up -d --build` fully recovers you. Nothing
irreplaceable lives on the VPS except the Redis queue (in-flight Celery
tasks) and Caddy's TLS cert cache (which just re-issues on next boot).

## Known limitation of this guide

Not yet covered: automated CI/CD (currently you `git pull` + rebuild by
hand), zero-downtime deploys (container restart causes a few seconds of
downtime on `backend-web`/`frontend`), and multi-server scaling. All three
are reasonable follow-ups once the single-VPS setup is proven out, not
day-one requirements for this traffic level.
