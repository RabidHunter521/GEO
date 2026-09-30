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
