# Share-link insight, company identity, admin 2FA, Supabase cleanup, client-view accessibility

Date: 2026-09-30 · Branch: `claude/gifted-ritchie-h5vl6z` · Alembic head at start: `1a3fd284901c`

Decisions taken with Faris (2026-09-30):
- Company line: **P&I Digital Solution (202603129117)** — SeenBy is its trading name.
- 2FA: authenticator app (TOTP), enforced only once `ADMIN_TOTP_SECRET` is set, so
  the deploy cannot lock the admin out.
- Supabase: remove every repo reference; Faris dumps the project from his laptop,
  then deletes it himself. (A direct `pg_dump` from the cloud container is blocked:
  the network allows HTTPS only.)

Grounding (verified in code, not from memory):
- Share token lives on `Client.share_token` / `share_token_created_at`; resolved by
  `require_share_client` in `app/api/v1/client_view.py`; rotated/revoked in
  `app/services/share_link_service.py`. Regenerate already exists in
  `ShareLinkCard.tsx`.
- `noindex` already set: API `X-Robots-Tag` in `_view_headers`, frontend
  `robots: {index:false}` in `view/[token]/layout.tsx`. Referrer-Policy is the
  global `strict-origin-when-cross-origin`.
- No invoices exist anywhere in the codebase — nothing to footer there.
- Emails are HTML built in `email_service.py` / `digest_service.py` /
  `report_service.py`; `schema.json` is Claude-generated in `toolkit_service.py`.

## Tasks

1. **Link open tracking.** `clients.share_last_viewed_at`, `share_view_count`
   (migration). The view layout's overview fetch records a view; a new "visit" is
   counted (and logged to activity) only if the previous one was >30 min ago.
   Admin previews are excluded by an `X-SeenBy-Admin-Preview` header sent when the
   viewer has an admin session. Surface "Client last opened the link 2 days ago ·
   N visits" in ShareLinkCard and on client detail.
   Success: tests for first view, throttled repeat, admin preview ignored.
2. **Link expiry.** `clients.share_token_expires_at` (nullable). Expired → the same
   uniform 404. ShareLinkCard: expiry picker (never / 7 / 30 / 90 days) on generate
   and regenerate; shows "Expires in N days" / "Expired".
   Success: tests for expired 404, null = never, rotation resets expiry.
3. **View headers.** `Referrer-Policy: no-referrer` on `/view/*` (Next headers +
   API `_view_headers`); add `X-Robots-Tag: noindex` at the Next layer too.
   Success: curl of a /view page shows both headers.
4. **Company identity in footers.** `COMPANY_LEGAL_NAME`,
   `COMPANY_REGISTRATION_NUMBER` constants (backend + frontend mirror); rendered in
   PDF report footer, digest + report email footers, `/view` footer.
5. **Client legal identity.** Optional `clients.legal_name`,
   `registration_number` (migration), admin-only (never in client_view schemas,
   never in scan queries). `schema.json` gets `legalName` + `identifier`
   deterministically after generation.
6. **Admin TOTP 2FA.** `otpauth` in NextAuth credentials `authorize`; login form
   code field; `scripts/generate-totp-secret` prints secret + otpauth URL.
   Success: unit tests on verification; no secret set = unchanged behaviour.
7. **Supabase removal.** Scrub references from code, CI, env examples,
   docker-compose, live docs (dated historical plans left as history).
8. **Accessibility CI.** Playwright + `@axe-core/playwright` against every
   `/view/[token]/*` page, served by `next start` against a fixture mock API.
   Runs in CI and blocks the build.
9. **Colour never alone + contrast.** Score colours always paired with band
   label; check yellow text contrast.
10. **Phone 375px + keyboard.** Screenshot every view page at 375px via the task-8
    harness and fix overflow/tap targets; add skip-to-content link.
11. **Loading/empty states + motion/readability.** `loading.tsx` skeletons for
    view routes; client-view body text ≥16px; reduced motion respected.

Waived: per-component Storybook pages (item 6 of the a11y list) — open-ended;
proposed as a follow-up phase once the axe harness shows where inconsistency is.

## Ledger (2026-09-30)

| # | Task | Commit(s) |
|---|---|---|
| 1 | Link open tracking | b777838 (migration 12960c0a6720) |
| 2 | Link expiry | 019e3b9 (migration 283e6ea1f8c7) |
| 3 | no-referrer / noindex headers | 1cb90ff |
| 4 | Company identity in footers | b26f935 |
| 5 | Client legal identity + schema.json | 104c6ad (migration b16c2c6690fe) |
| 6 | Admin TOTP 2FA | a9b8552 |
| 7 | Supabase references removed | 3797976 |
| — | Pre-existing CI reds: next critical advisory, missing RESEND_API_KEY | 0d35c13, deb08c6 |
| 8–10 | Contrast/colour-alone/skip link; axe + 375px CI gate | c33cea4, 973c309, eebb342 |
| 11 | Loading skeletons, 16px client-view body text | 25b2acc |

Deviations:
- Regenerating a link keeps visit history (it describes the client, not a token).
- Regenerate keeps its one confirmation dialog: it breaks the link the client has.
- Truth Vault legal-name fact not added; schema.json gets the identity directly.
- No invoices exist, so no invoice footer.

Verified: backend 2133 tests (CI env), ruff clean, one alembic head, frontend
typecheck + 151 unit tests + build, axe/375px gate 16/16 locally, 2FA end to end
on a production build. NOT verified: the new `a11y` CI job on GitHub (CI runs
on PRs / master only), migrations on production (run on next api boot).

Open, not in this phase:
- The Alembic chain cannot build an empty database (first revision assumes
  pre-existing tables), so CI `migrations` stays red. Needs a baseline
  migration checked against production's real schema via `railway ssh`.
- Overview "Wins" can list the same AI quote twice (seen on Medilink demo).
- Per-component Storybook pages (a11y item 6) — waived, follow-up phase.
