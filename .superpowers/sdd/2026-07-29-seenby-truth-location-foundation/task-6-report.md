# Task 6 Report — Location and Truth Vault administration

**Status:** implemented and verified

## Delivered

- Added the admin-only route at `/clients/[id]/reputation/truth` and exposed it
  under the existing Reputation navigation group as **Business Truth**.
- Added exact serializable frontend contracts for locations, truth facts,
  versions, status, scope, values, and effective/approval dates. Draft
  `reviewer_note` is deliberately not exported in public frontend types.
- Added server-only API adapters for location CRUD and truth fact history,
  creation, drafting, approval, and retirement; client mutations go through
  route-local server actions only.
- Implemented Brand-wide/active-location scope selection, location creation,
  editing, deactivation, and an explicit primary-location reassignment
  confirmation.
- Implemented six fact groups: Identity, Contact, Offering, Credentials,
  Policies, and Sources. Saving values creates a draft; a separate approval
  dialog requires an approver and displays the draft source/effective date for
  confirmation. Version history is display-only.
- Stale or hand-crafted inactive-location query strings resolve safely to the
  Brand-wide scope instead of showing inactive facts under an incorrect label.

## Verification

TDD was used where the frontend's Node unit harness supports it:

1. Added the expected Truth Vault navigation item to the navigation contract.
2. Observed the test fail because `/reputation/truth` was absent.
3. Added the navigation item and observed the test pass: **6/6**.

The repository has no DOM component-test project, so component behaviour is
validated by the production compiler/build rather than an unsupported test
environment.

Fresh checks:

```text
npx.cmd vitest run --project unit src/lib/__tests__/navigation.test.ts
6 passed

npm.cmd run typecheck
exit 0

npm.cmd run build
exit 0; /clients/[id]/reputation/truth emitted as a dynamic route
```

## Scope notes

- No backend, schema, migration, client-visible route, or dependency changes.
- Location hours/service-area/coordinates are mirrored in the API types for
  contract completeness; the initial admin form covers the primary operational
  location fields (name, address, country, contact, website, booking URL).

## Commit

Planned commit message: `feat: add truth vault administration`.
