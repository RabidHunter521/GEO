# CLAUDE.md — SeenBy MVP

Behavioral guidelines for this project. Built on top of the base CLAUDE.md principles.

## 1. Project Context

SeenBy is an agency-model AI visibility tracking platform.
- Stack: Next.js 15 + FastAPI + PostgreSQL + Celery + Redis
- You (Faris) are the only admin. There is no client-facing login in MVP.
- All scans are on-demand, manually triggered by you.
- Clients receive reports via email only — no dashboard access.

When in doubt about scope, refer to the MVP scope in `/docs/mvp-scope.md`.

## 2. Language Rules (enforce everywhere)

These are non-negotiable. Never use the left column in any UI text, email, 
copy, or comment that surfaces to clients.

| Never use | Always use |
|---|---|
| cited / uncited | Seen by AI / Not seen by AI |
| mentioned / not mentioned | Seen by AI / Not seen by AI |
| citation rate | visibility frequency |
| ranking position | AI Search Ranking |
| visibility gap | Your competitors are winning here |
| confidence score | (never surface to client) |
| char offset | (never surface to client) |
| token count | (never surface to client) |
| first mentioned | first seen by AI |

## 3. Score Band Constants

Use these exact values everywhere. Do not hardcode magic numbers.

```python
# backend/app/core/constants.py
SCORE_BANDS = {
    "excellent": (80, 100),
    "good":      (65, 79),
    "fair":      (50, 64),
    "developing":(35, 49),
    "low":       (0,  34),
}

# SCORE_BANDS drive labels only. Color is a separate 3-band traffic light
# keyed off the raw score, independent of the named bands:
#   0–29  → red
#   30–69 → yellow
#   70–100 → green
# Frontend: getScoreColor() in src/lib/score-utils.ts
# Backend:  get_score_color() in app/services/scoring_service.py
```

## 4. GEO Score Dimensions

The overall score is computed from 5 dimensions. Never change weights 
without updating this file and bumping SCORE_VERSION.

| Dimension | Weight | Source |
|---|---|---|
| AI Citability | 40% | Automatic — scan engine |
| Brand Authority | 20% | Assisted — Claude-suggested, admin-reviewed |
| Content Quality | 20% | Assisted — Claude-suggested, admin-reviewed |
| Technical Foundations | 10% | Auto — AI Readiness Toolkit verified |
| Structured Data | 10% | Auto — AI Readiness Toolkit verified |

Manual dimensions must always show label: "Based on public evidence · Reviewed by SeenBy"
SCORE_VERSION = "v1.2.0" — bump when weights or formula change.
(v1.1.0: AI Citability = equal-weighted average of per-platform visibility
across the client's enabled platforms; unavailable platforms are excluded.)
(v1.2.0: Brand Authority + Content Quality sourcing changed from bare admin
input to assisted, human-reviewed scoring — Claude suggests, admin gates every
number; weights unchanged.)

## 5. Scan Engine Rules

- Up to 20 queries per platform per scan (5 per category × 4 categories), run on
  every enabled platform. Comparison queries are capped by the number of
  competitors (max 5), so a client with no competitors runs 15.
- 4 platforms: chatgpt, perplexity, gemini, claude (per-client toggle in settings, ≥1 required)
- Retry once on API failure, flag if fails again
- If one platform fails entirely, the scan still completes: score uses the
  remaining platforms, the platform is marked unavailable, activity is logged
- Store raw responses for 90 days
- Max 5 competitors per client
- Scans are ON-DEMAND only — no scheduled scans in MVP

Query categories:
1. brand (direct brand name queries)
2. comparison (brand vs competitor)
3. recommendation (best X in industry)
4. local (best X in KL/Malaysia)

## 6. AI Readiness Toolkit Rules

Three generators powered by Claude API:
- llms.txt — Answer.AI spec
- schema.json — JSON-LD LocalBusiness + Organization + FAQPage
- robots.txt — allow GPTBot, PerplexityBot, ClaudeBot, Google-Extended

After generation:
- Always show copy + download buttons per file
- Always show plain English implementation instructions per file
- Verification crawler must check clientdomain.com/llms.txt etc.
- On verified: auto-update Technical Foundations + Structured Data scores

## 7. Email Rules

Weekly digest (automated):
- Sender: contact@seenby.my
- Trigger Claude-generated action ONLY when score changes ±5pts
- Otherwise send standard tip
- Subject line must include the client's visibility score

Monthly PDF report:
- Auto-generated via WeasyPrint
- You (Faris) review before sending
- Sent 30 days after signup, then every 30 days
- Contact email: contact@seenby.my (not hello@seenby.my)
- Includes a Claude "what changed this month" narrative, generated once at
  report build, persisted on the report, and shown in the PDF + share view

Admin alerts (score drop / competitor overtake / hallucination):
- Always email ALERTS_EMAIL; also push to Telegram when TELEGRAM_BOT_TOKEN +
  TELEGRAM_CHAT_ID are set (best-effort, never blocks a scan)

## 8. File + Data Rules

- PDF reports stored in Cloudflare R2 — never in Postgres as base64
- Raw scan responses retained 90 days, then purged
- Client data archived 6 months after churn, then auto-deleted
- Never expose: confidence scores, char offsets, token counts, 
  raw API responses to any client-facing surface

## 9. Admin Panel Navigation

Exact structure — do not add pages without updating this:
/                        → redirect to /clients
/clients                 → all clients overview
/clients/gap-matrix      → cross-client competitor gap matrix
/clients/[id]            → client detail
/clients/[id]/scan       → scan & visibility
/clients/[id]/competitors→ competitor intelligence
/clients/[id]/toolkit    → AI readiness toolkit
/clients/[id]/content-gaps→ content gaps (topic + entity coverage, content quality assist)
/clients/[id]/content-roadmap→ 90-day content roadmap (competitor lost-query driven)
/clients/[id]/reports    → reports
/clients/[id]/activity   → activity log
/clients/[id]/settings   → client settings (incl. client view link controls)
/auth/login              → admin login only

Public read-only client view (no login — gated by 256-bit share token in the
URL; uniform 404 on invalid/revoked/archived; whitelisted schemas only, never
raw AI responses or internal fields):
/view/[token]             → client overview (score, dimensions, traffic, history)
/view/[token]/scan        → scan & visibility results
/view/[token]/competitors → competitor comparison
/view/[token]/reports     → delivered PDF reports

## 10. Coding Conventions

### Backend (FastAPI)
- All routes in `app/api/v1/`
- Business logic in `app/services/` — never in routes
- Constants in `app/core/constants.py`
- One model file per domain entity
- Alembic migration for every schema change — no raw ALTER TABLE

### Frontend (Next.js)
- shadcn/ui components only — no custom component library
- All API calls through `src/lib/api.ts` — never fetch directly in components
- All types in `src/types/index.ts`
- Score bands and colors from constants — never hardcoded

### Workers (Celery)
- One task file per domain: scan_tasks, report_tasks, alert_tasks, digest_tasks
- Always use `return_exceptions=True` in asyncio.gather
- Log task start + end with structlog
- Never import frontend or backend app directly — shared logic goes in workers/engine/

## 11. What NOT to build in MVP

If asked to implement any of the following, stop and confirm with Faris first:

- Client dashboard login
- Self-serve signup or billing (Stripe)
- White-label / reseller features
- Multi-locale prompts
- Scheduled / automated scans
- Webhook integrations
- Twice-daily scan frequency

Note: Brand Authority / Content Quality shipped as assisted, human-reviewed scoring (admin gates every number) — fully automated scoring is still out of scope.

## 12. Base CLAUDE.md Principles Still Apply

1. Think before coding — state assumptions, surface tradeoffs
2. Simplicity first — minimum code that solves the problem
3. Surgical changes — touch only what you must
4. Goal-driven execution — define success criteria before starting