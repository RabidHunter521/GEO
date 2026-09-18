# New machine setup

How to move development of SeenBy to a new laptop without losing anything.
Everything in git is on GitHub (`RabidHunter521/GEO`); this runbook covers the
parts that are **not** in git, plus the toolchain.

This doc contains no secrets. Never paste real `.env` values into it.

## 0. What lives only on the old machine

These files are git-ignored on purpose. If they are lost, the fallbacks in the
right-hand column are the only way to recover them.

| Path | What it is | If lost |
|---|---|---|
| `backend/.env` | API keys (Anthropic, Gemini, OpenAI, Perplexity, Resend), Cloudflare R2, `ADMIN_API_KEY`, `DATABASE_URL`, `REDIS_URL` | Copy from Railway: `railway variables -s api`. Rotate anything you cannot find. |
| `frontend/.env.local` | `AUTH_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `API_BASE_URL`, `ADMIN_API_KEY` | `railway variables -s frontend`; `AUTH_SECRET` can be regenerated for local use. |
| `docs/ops/pre-migration-backups/` | JSON snapshots of the production DB taken before risky migrations | Not recoverable. Back these up. |
| `.claude/settings.local.json` | Claude Code permission allowlist + local env overrides | Recreate by accepting prompts; see step 7. |
| `~/.claude/` (user home) | Claude Code memory for this project, global skills, agents, `settings.json`, RTK config | Memory is not recoverable. Back the whole folder up. |

Templates for both env files are tracked: `backend/.env.example`,
`frontend/.env.local.example`.

## 1. On the old machine

1. Confirm nothing is unpushed. Both commands must print nothing:

   ```bash
   git status --porcelain
   git log origin/master..master --oneline
   ```

   Also check for local branches with unpushed commits and stashes:

   ```bash
   git for-each-ref --format='%(refname:short) %(upstream:short)' refs/heads/
   git stash list
   ```

2. Copy the five items from the table above to a password manager / encrypted
   drive. Do not email them to yourself and do not commit them.

3. Sign out of GitHub, Railway, OneDrive and Claude Code, then wipe the disk.
   `backend/.env` holds live billing-capable API keys — treat the old disk as
   compromised until it is wiped.

## 2. Install the toolchain

Versions in use as of 2026-09 (newer is fine unless noted):

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | |
| Node.js | 24.x (npm 11) | frontend |
| Python | 3.12+ | `backend/pyproject.toml` pins `^3.12` |
| Poetry | 2.x | must be on `PATH` — `.claude/launch.json` and the `run-app` skill call plain `poetry` |
| Railway CLI | 5.x | `railway login`; needed for every prod question |
| Docker Desktop | any | local Redis via `docker-compose.yml` |
| GitHub CLI (`gh`) | optional | PR workflow |
| Claude Code desktop | latest | |

On Windows, install Poetry with the official installer and make sure
`%APPDATA%\Python\Scripts` is on `PATH`, then check:

```bash
poetry --version
```

WeasyPrint (PDF reports) needs GTK/Pango libraries on Windows. If
`poetry run python -c "import weasyprint"` fails, install the GTK3 runtime;
PDF tests silently skip when the toolchain is missing, so check this
explicitly.

## 3. Clone

Clone **outside OneDrive / any synced folder**. `node_modules` and `.venv`
inside a synced folder thrash the sync client and slow every install.

```bash
git clone https://github.com/RabidHunter521/GEO.git "C:\dev\seenby"
cd "C:\dev\seenby"
```

## 4. Restore the git-ignored files

Put each file back at the same relative path:

- `backend/.env`
- `frontend/.env.local`
- `docs/ops/pre-migration-backups/*.json`
- `.claude/settings.local.json`

Then fix `DATABASE_URL` in `backend/.env`. The old copy pointed at a stale
Supabase project that is **not** production (see CLAUDE.md §8). Point it at a
local Postgres or a throwaway database. Production is only ever reached through
`railway ssh`, never through a local `.env`.

## 5. Restore Claude Code state

1. Copy the backed-up `~/.claude/` folder to `C:\Users\<you>\.claude\`.
2. Sign in to Claude Code (the old `.credentials.json` will not carry over).
3. Project memory lives at
   `~/.claude/projects/<slug-derived-from-project-path>/memory/`. The slug is
   the absolute project path with separators replaced by `-`. If the new path
   differs from the old one, open the project once in Claude Code, find the
   new folder it created under `~/.claude/projects/`, and move `MEMORY.md` and
   the `*.md` memory files from the old slug folder into it.
4. Open `.claude/settings.local.json`. If it sets `ANTHROPIC_BASE_URL` to a
   `127.0.0.1` address, that was a local proxy on the old machine — delete the
   line unless you reinstall the proxy, otherwise Claude Code cannot connect.

## 6. Install dependencies

```bash
cd backend && poetry install
```

```bash
cd frontend && npm install
```

## 7. Run it

Start Redis:

```bash
docker compose up -d redis
```

Then either use the `/run-app` skill in Claude Code, or manually:

```bash
cd backend && poetry run uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

Check `http://localhost:8000/docs` and `http://localhost:3000`. Accept the
Claude Code permission prompts as they come; they rebuild
`.claude/settings.local.json`.

## 8. Verify production access

This is the only check that matters for real work:

```bash
railway ssh -s api -- alembic current
```

It must print the same revision as `cd backend && poetry run alembic heads`.
If `railway` cannot find the project, run `railway link` inside the repo.

## 9. Run the test suites once

```bash
cd backend && poetry run pytest -q
```

```bash
cd frontend && npx tsc --noEmit
```

Both green means the new machine matches the old one. Then read
`docs/architecture.md` and the latest handoff memory before touching code.
