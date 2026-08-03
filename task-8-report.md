# Task 8 — Public truth and location summaries

Implemented the share-token endpoint `GET /api/v1/view/{token}/truth-health`
and its reputation-page presentation.

The response is a strict public whitelist:

- active location name, city, rendered opening-hours summary, and approved
  `service_categories` only;
- most-recent current-fact approval/effective timestamp as freshness;
- generic summaries and counts for human-reviewed, fact-backed conflicts in
  `confirmed`, `corrected`, or `verified_fixed` states.

It structurally excludes drafts, raw fact values other than service categories,
fact/version identifiers, source URLs and source metadata, reviewer notes,
approval identities, raw AI quotes, severity, explanations, and admin notes.
Unreviewed `suggested` and automated `candidate_fixed` conflicts are omitted.
Prospect links continue to receive the public-view 404.

Verification completed:

- `backend/.venv/Scripts/python.exe -m pytest tests/test_client_view_truth.py -vv` — 2 passed
- `npx.cmd vitest run src/lib/__tests__/view-reputation-truth.test.ts --project unit` — 1 passed
- `npm.cmd run typecheck` in `frontend` — passed
