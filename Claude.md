# CLAUDE.md — SeenBy MVP

Behavioral guidelines for this project. Built on top of the base CLAUDE.md principles.

## 1. Project Context

SeenBy is an agency-model AI visibility tracking platform.
- Stack: Next.js 15 + FastAPI + PostgreSQL + Celery + Redis
- You (Faris) are the only admin. There is no client-facing login in MVP.
- All scans are on-demand, manually triggered by you.
- Clients receive reports via email only — no dashboard access.

When in doubt about scope, refer to the MVP scope in `/docs/mvp-scope.md`.
For a one-page code map (flows, layers, where to start for common changes), read `/docs/architecture.md` before exploring.

Project skills (in `.claude/skills/`): `seenby-workflow` (start of any coding task),
`seenby-verify` (definition-of-done gate), `seenby-demo-check` (pre-pitch demo audit),
`seenby-release` (prod deploy + Supabase migration runbook),
`seenby-prompts` (any LLM prompt work — standards + checklist),
`seenby-migrations` (Alembic runbook — revision IDs, RLS, test bootstrap),
`seenby-phase` (executing multi-task roadmap phases with review gates),
`seenby-debug` (evidence-first debugging paths per subsystem),
`seenby-client-output` (quality rules for anything a client sees). Use them.

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
SCORE_VERSION = "v1.3.0" — bump when weights or formula change.
(v1.3.0: AI Citability counts a brand as seen only when an answer mentions it
for a reason OTHER than denying knowledge of it. Brand-category queries contain
the brand name, so models echo it back while saying "X does not appear to be a
recognized company" — a plain regex match scored that as visibility and
inflated the heaviest dimension worst for the least-visible clients.
`detect_brand_in_answer` (denial blocklist, sentence-scoped) is used for AI
answers; `detect_brand_mention` stays the pure matcher for CRAWLED PAGE TEXT.
Stance only — a positive but wrong answer still counts, since truthfulness is
handled separately by `hallucination_flagged`. Weights unchanged. Expect
existing clients' AI Citability to FALL on their next scan; historical scores
were computed under v1.2.0 and are not recomputed.)
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

### Database access posture (settled 2026-07-28)

- The app connects to Supabase as `postgres`, which has `bypassrls = true`.
  There is no Supabase client, anon key, PostgREST call or Supabase Auth
  anywhere in the codebase.
- Supabase's `anon` and `authenticated` roles had full DML — including
  TRUNCATE — on all 27 tables by default. Migration `d3f7a1c58e02` revoked
  those and the default privileges that re-granted them on every new table.
  Do not re-grant them without a real reason: RLS does NOT restrict TRUNCATE,
  so those grants were a data-loss path that RLS could not cover.
- **RLS is enabled on every table with ZERO policies.** That is deliberate:
  with no client login there is nothing to write a policy for, and enabled +
  no policy denies every non-bypassing role. It is defence in depth, not the
  active control — the active control is that only `postgres` connects.
  Never describe RLS to a client as protecting their data today.
- **New tables do NOT get RLS automatically.** Every migration creating a
  table must `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` inline, as all
  existing ones do. CI fails the build if any table lacks it.

## 9. Admin Panel Navigation

Exact structure — do not add pages without updating this:
/                        → redirect to /clients
/clients                 → all clients overview
/gap-matrix              → cross-client competitor gap matrix
/review-queue            → cross-client work-log inbox (pending suggestions)

Global (non-client-scoped) admin pages live at the TOP LEVEL, inside the
`src/app/(admin)/` route group so they share the sidebar + auth layout.
`/clients/*` means client-scoped. A route group's parentheses do not appear in
the URL. `/clients/gap-matrix` permanently redirects to `/gap-matrix`.

/clients/[id]            → client detail
/clients/[id]/scan       → scan & visibility
/clients/[id]/competitors→ competitor intelligence
/clients/[id]/toolkit    → AI readiness toolkit
/clients/[id]/content-gaps→ content gaps (topic + entity coverage, content quality assist)
/clients/[id]/content-roadmap→ 90-day content roadmap (competitor lost-query driven)
/clients/[id]/content-studio→ content studio (page citability audits + content deliverables)
/clients/[id]/authority  → authority & presence (directory/review/social checklist, provenance-prioritised)
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
/view/[token]/progress    → delivery timeline (published work log only)

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
- Tasks live in `backend/workers/tasks/`, one file per domain: scan_tasks,
  report_tasks, digest_tasks, content_tasks, maintenance_tasks. There is no
  alert_tasks — alerting is synchronous, best-effort, and runs inline from the
  scan flow (`app/services/alert_service.py`, called by `run_scan`).
- Shared business logic lives in `app/services/`; worker tasks are thin
  entrypoints that open a DB session and delegate to a service. There is no
  `workers/engine/`. Tasks may import `app.services.*` (the backend app), but
  never the frontend.
- When fanning out concurrent work that can partially fail, isolate each unit so
  one failure can't sink the batch (the scan engine uses a ThreadPoolExecutor
  with per-future try/except; for asyncio.gather use `return_exceptions=True`).
- Log task start + end with structlog.
- Best-effort post-commit steps (alerts, action-center refresh) must catch,
  `db.rollback()`, and swallow — a failed notification never undoes a good scan.

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

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->