# Team accounts (multi-admin), workspace-ready

Date: 2026-09-30 · Branch: `claude/gifted-ritchie-h5vl6z` · Alembic head at start: `b16c2c6690fe`

## Goal

Faris can invite staff as admins. Every admin has their own login and
mandatory 2FA, the API knows which person made each request, some actions
are owner-only, and the activity log records who did what. Built so that
separate agency workspaces can be added later without reworking it: the
`workspaces` table, `workspace_id` columns and the token's workspace claim
exist from day one, with a single workspace ("SeenBy").

Out of scope (agency phase, later): filtering all 155 admin routes by
workspace plus the cross-workspace route test, workspace-scoped global
pages, per-workspace alert/cost settings, per-workspace branding.

## Decisions (Faris, 2026-09-30)

- Staff now; independent agencies later.
- Invites by email link (48 h, one-time); the invitee sets their own password.
- 2FA (authenticator app) mandatory for every user, set up during invite
  acceptance, so no account can exist without it.
- Owner-only (defaults, Faris had no preference): manage users, archive
  clients, benchmark publishing (approve / publish / withdraw). Staff can do
  everything else, including scans and sending reports. Cost caps are
  environment variables today, so there is no route to restrict.

## Design

- **Users:** `users` (email unique, name, argon2 `password_hash`, `role`
  owner|staff, `workspace_id`, `totp_secret`, `totp_confirmed_at`,
  `last_totp_step`, `failed_logins`, `locked_until`, `is_active`,
  `invite_token_hash`, `invite_expires_at`, `last_login_at`). Invite and
  password reset share one mechanism: a one-time link that sets password + 2FA.
- **Workspaces:** `workspaces` with one row, id = `DEFAULT_WORKSPACE_ID`
  constant. `clients.workspace_id` NOT NULL, backfilled to it.
- **Login:** NextAuth `authorize` calls `POST /api/v1/auth/login` (service
  call, authenticated with ADMIN_API_KEY). The backend checks password
  (argon2), lockout (5 failures → 15 min, in the DB), TOTP (±1 step, replay
  rejected via `last_totp_step`), and `is_active`.
- **Cut-over without lock-out:** while NO active user exists, the backend
  answers 409 `no_users` and the frontend falls back to today's env login
  (ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_TOTP_SECRET). The moment the owner
  account exists, the env login stops working by itself. Owner bootstrap:
  `railway ssh -s api -- python -m scripts.create_owner <email> <name>`
  prints an invite link.
- **Per-request identity:** the Next server mints a 5-minute HS256 JWT
  (`sub`, `wid`, `role`, `aud=seenby-api`) for each API call, signed with a
  key derived from ADMIN_API_KEY (HMAC with a fixed label, so the raw key is
  never the JWT key). The backend verifies it, loads the user (so
  deactivation is immediate), and exposes it via a request-scoped contextvar.
  The raw ADMIN_API_KEY bearer stays accepted during the transition as the
  "system" caller; removing it is the last task, after the owner exists in
  production.
- **Actor:** a SQLAlchemy `before_insert` hook stamps
  `activity_log.actor_user_id` from the contextvar, so every existing
  ActivityLog call site is covered without touching it. Celery = no actor
  ("System"). Also `work_log_entries.published_by_user_id`,
  `reports.sent_by_user_id`.
- **RLS:** every new table enables RLS inline, anon REVOKE guarded
  (CLAUDE.md §8). Isolation today is by application code; RLS stays the
  defence-in-depth layer.

## Tasks

1. **Schema.** Models `Workspace`, `User`; `clients.workspace_id`;
   `activity_log.actor_user_id`; `work_log_entries.published_by_user_id`;
   `reports.sent_by_user_id`. One migration, RLS inline, backfill to the
   default workspace. Register models in `tests/conftest.py`.
   Success: migration applies on a fresh create_all DB + upgrade from
   `b16c2c6690fe` on a Postgres copy; one head; CI RLS check passes.
2. **Auth core (service).** `user_service`: argon2 hashing, invite create /
   inspect / accept, authenticate (lockout, TOTP replay), reset, deactivate.
   `pyotp` + `argon2-cffi` dependencies. Success: unit tests for every path,
   including wrong code, replayed code, locked, inactive, expired invite.
3. **Auth API + owner bootstrap.** `/auth/login`, `/auth/invite/{token}`
   (inspect, generates the pending TOTP secret), `/auth/invite/{token}/accept`;
   `scripts/create_owner.py`; invite email from contact@seenby.my.
   Success: API tests; 409 `no_users` before any user exists.
4. **Request identity.** `require_api_key` accepts the signed JWT or the raw
   key; current-user contextvar; `require_owner` dependency. Success: tests
   for valid / expired / wrong-audience / deactivated-user tokens.
5. **Frontend auth.** NextAuth → backend login with env fallback; session
   carries id/role/workspace; `api.ts` (and the two direct-fetch route
   handlers) send the per-request JWT; public `/auth/invite/[token]` page
   with QR code; login form email + password + code. Success: production
   build, end-to-end invite → accept → login → API call as that user.
6. **Roles.** Owner-only routes (users, archive client, benchmark
   publishing); UI hides those controls from staff. Success: staff 403 tests.
7. **Team page** `/team` (owner): list, invite, resend, reset, deactivate.
   Sidebar entry for the owner. Success: e2e on a production build.
8. **Who did what.** Actor on activity log, work-log publish, report send;
   shown in the activity feed and delivery views.
9. **Docs + cut-over.** CLAUDE.md §1/§9, DEPLOYMENT (owner bootstrap),
   release notes. After Faris's owner account works in production: remove
   the raw ADMIN_API_KEY bearer from admin routes and the env login.

## Ledger (2026-09-30)

| # | Task | Commit(s) |
|---|---|---|
| 1 | Schema (migration b956747aed6c) | c663e0a |
| 2 | Account service | fdad62f |
| 3 | Auth API, invite email, owner bootstrap | d418747 |
| 4 | Per-request identity | fc31487 |
| 5 | Frontend sign-in, per-user token, invite page | a1a6242, 2c3daa9 |
| 6 | Owner-only actions | 1c8da6b |
| 7 | Team page | 0e64669 |
| 8 | Who did what | b998b63, 369c5d6 |
| 9 | Docs (this) | — |

Deviations:
- Cut-over needs no terminal: while signed in with the legacy login you are
  the owner, so the Team page can invite your own owner account.
  `scripts/create_owner` stays as the fallback.
- DEFAULT_WORKSPACE_ID starts with a letter: SQLite stores an all-digit
  hex UUID as REAL, which broke FK matches in tests.
- Staff may archive prospects (cold leads); paying clients are owner-only.
- An API 401 for a signed-in admin ends the session (/auth/session-ended).
- Scan events are written by Celery and read as "System".

Verified: backend 2190 tests; frontend 151 unit tests, typecheck, build;
migration upgrade/downgrade/re-upgrade on Postgres with seeded data;
end to end on production builds: legacy login → owner setup → legacy login
refused; invite/accept validation; replayed code; staff restrictions;
deactivation signs the admin out; self-invite cut-over from the Team page.
NOT verified: production (migration runs on the next api boot).

Remaining (task 9b, after the owner account works in production): remove
the raw ADMIN_API_KEY bearer from admin routes (keep it only for the
service-only /auth routes) and delete the legacy env login code.
