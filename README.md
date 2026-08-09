# SeenBy

SeenBy is an agency-model AI visibility tracking platform. It tells brands
whether AI assistants — ChatGPT, Perplexity, Gemini, and Claude — are
recommending them, and gives agencies a concrete plan for what to do about it
if they're not.

See [`docs/FEATURES.md`](docs/FEATURES.md) for the full feature list and
[`docs/mvp-scope.md`](docs/mvp-scope.md) for what's in scope for the current
build.

## Stack

- **Frontend** — Next.js 15, shadcn/ui
- **Backend** — FastAPI (Python)
- **Database** — PostgreSQL (Supabase in production)
- **Background jobs** — Celery + Redis
- **Production hosting** — Railway (API, worker, beat, frontend) — see
  [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

This is an MVP with a single admin (no client-facing login). Clients receive
results via email and a read-only, share-token-gated view — never a login.

## Repository layout

```
backend/     FastAPI app — routes (app/api/v1), business logic (app/services),
             SQLAlchemy models, Alembic migrations, Celery tasks (workers/)
frontend/    Next.js 15 admin panel + public client view (src/app, src/lib,
             src/components, src/types)
docs/        All project documentation (see below)
.claude/     Claude Code skills and settings used for this project
.github/     CI workflow
```

### `docs/` map

| Folder | What's in it |
|---|---|
| `docs/DEPLOYMENT.md` | Production deploy runbook (Railway + Supabase) |
| `docs/architecture.md` | One-page code map — flows, layers, where to start |
| `docs/mvp-scope.md` | What's in / out of scope for the MVP |
| `docs/FEATURES.md` | Full feature overview |
| `docs/methodology.md` | How the Growth Readiness score is calculated |
| `docs/business/` | Investor/stakeholder-facing overview, positioning |
| `docs/demo/` | Demo walkthrough script |
| `docs/marketing/` | Marketing content drafts (social, etc.) |
| `docs/templates/` | Client-facing templates (proposals, SOPs, onboarding) |
| `docs/ops/` | Operational runbooks (release checklist, privacy) |
| `docs/plans/`, `docs/superpowers/plans/`, `docs/superpowers/specs/` | Dated design/implementation plans, kept as a historical record of how each feature was built |

## Running locally

```bash
cd frontend && npm run dev      # http://localhost:3000
cd backend && poetry run uvicorn app.main:app --reload --port 8000   # http://localhost:8000
```

API docs: `http://localhost:8000/docs`

## Conventions

Project-specific rules (language rules for client-facing copy, score
constants, coding conventions, admin panel route map) live in
[`CLAUDE.md`](CLAUDE.md) — read it before making changes.
