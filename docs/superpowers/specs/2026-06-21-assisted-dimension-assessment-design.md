# Assisted Dimension Assessment — Design Spec

**Date:** 2026-06-21
**Status:** Approved for planning
**Author:** Faris (with Claude)

## Problem

Brand Authority (20%) and Content Quality (20%) — 40% of the GEO score — are
currently set by hand and labeled "Assessed by SeenBy team." Clients cannot
verify the number or see how to improve it, and because SeenBy both sells the
service and assigns 40% of the score that measures the service's value, a
sophisticated client may suspect the number is inflated to justify the retainer.

## Goal

Make the two manual dimensions **evidence-backed and expert-reviewed**: Claude
computes a *suggested* score plus concise evidence, the admin reviews and
accepts (or adjusts), and the client sees the evidence behind the number. This
removes the conflict-of-interest smell, gives the client a path to improve, and
preserves the human-expert premium that justifies the retainer.

This is **assisted, human-reviewed scoring** — NOT fully automated scoring. The
admin remains the gate on every number that reaches a client.

## Decisions (locked)

| Decision | Choice |
|---|---|
| Scoring engine | Claude API assessment, reusing `geo-brand-mentions` + `geo-content` rubrics as prompts |
| Governance | Suggestion is a **draft**; admin must accept/adjust before it counts toward the GEO score |
| Trigger | **On-demand** "Generate assessment" button per client (no auto/cadence in MVP) |
| Client exposure | **Concise evidence summary** — 3–5 plain-English bullets per dimension, labeled "Evidence-based · Reviewed by SeenBy" |

## Architecture & Flow

```
[Admin clicks "Generate assessment" on client]
        │
        ▼
AssessmentService.run(client, dimension)
   → Claude API (rubric prompt + fetched client web context)
   → { suggested_score, evidence_bullets[], raw_narrative }
        │
        ▼
Stored as a DimensionAssessment row  (status = "suggested")
        │
   Admin reviews in panel ──► Accept  ──► copy score+evidence to client.*  (status = accepted)
                          └─► Adjust ──► admin types final score          (status = adjusted)
        │
        ▼
GEO score recomputed · evidence bullets surface in client view
```

The accepted score still lands in `client.brand_authority_score` /
`client.content_quality_score`, where `compute_geo_score()` already reads it. The
scoring **formula is unchanged**; only how the number is *proposed* changes. This
keeps the blast radius small.

## Data Model

New table (Alembic migration — no raw ALTER per §10):

```
DimensionAssessment
  id                uuid pk
  client_id         uuid FK -> clients.id
  dimension         "brand_authority" | "content_quality"
  suggested_score   int          # Claude's output
  final_score       int | null   # what admin accepted/adjusted to
  evidence_bullets  JSON         # list[str], short, client-safe
  raw_narrative     Text         # Claude's full reasoning — ADMIN-ONLY, never client-facing
  status            "suggested" | "accepted" | "adjusted"
  generated_at      datetime
  reviewed_at       datetime | null
```

- **Accepted value stays on `client`** so scoring is untouched.
- **Suggestion + history live in the table** → built-in audit trail ("Claude
  suggested 58, you set 65 on 2026-06-21"), and re-runs never clobber history.
- **Client-facing evidence source of truth:** the client view reads
  `evidence_bullets` from the latest **accepted** `DimensionAssessment` row.
  The legacy `client.brand_authority_evidence` / `content_quality_evidence` text
  fields remain only as a **manual fallback** — shown when a dimension has no
  accepted assessment (admin typed evidence by hand). On accept, the assessment
  row is the canonical evidence; the text field is not overwritten.

## Backend

`app/services/assessment_service.py` — one method per dimension:
- Builds the rubric prompt from the `geo-brand-mentions` / `geo-content` scoring
  tables; sends client website + name + industry as context to the Claude API.
- Parses a structured JSON response: `{score, bullets[], narrative}`.
- Reuses the existing Claude client + `llm_call_log` cost tracking.
- Retry-once-then-flag on API failure (matches scan engine rule).
- Sanitizes bullets against §2 language rules (no "cited/mentioned/citation
  rate/ranking position", etc.) before storage.

Endpoints (routes in `app/api/v1/clients.py`, logic in the service):
- `POST /clients/{id}/assessments/{dimension}/generate` → runs Claude, stores a
  `suggested` row, returns the draft.
- `POST /clients/{id}/assessments/{dimension}/accept` → body optionally carries
  an adjusted score; sets the row's `final_score`/`status`/`reviewed_at`, writes
  the accepted score to `client.brand_authority_score`/`content_quality_score`,
  recomputes GEO score, logs to activity. Evidence stays canonical on the row
  (not copied to the `client.*_evidence` text field).
- `GET /clients/{id}/assessments` → latest draft + history for the panel.

**Guardrail:** `raw_narrative` is admin-only — never added to any `client_view`
schema. Only sanitized `evidence_bullets` are client-facing.

## Frontend

**Admin (client detail / settings):** a "Generate assessment" button next to each
manual dimension. After it runs, a review card shows *Suggested: NN*, the evidence
bullets, and **Accept** / **Adjust & accept** (number input). Accept writes
through and the GEO score updates. The existing free-text evidence box stays as a
manual fallback.

**Client view (`/view/[token]`):** under Brand Authority and Content Quality,
render accepted evidence bullets beneath a **"Evidence-based · Reviewed by
SeenBy"** label (replacing "Assessed by SeenBy team"). Add
`evidence_bullets: list[str]` to the whitelisted client-view dimension schema —
no new internal data exposed.

## Scoring, Label & Spec Impacts

- **`SCORE_VERSION` bump v1.1.0 → v1.2.0** — methodology of how two dimensions are
  *sourced* changed (formula weights unchanged), with a one-line changelog note.
- **Label swap in all 6 known locations:** "Assessed by SeenBy team" →
  "Evidence-based · Reviewed by SeenBy":
  - `frontend/src/app/clients/[id]/checklist/ChecklistClient.tsx` (×2)
  - `frontend/src/app/clients/[id]/page.tsx`
  - `frontend/src/app/clients/[id]/settings/SettingsForm.tsx` (×2 + helper copy)
  - `frontend/src/app/view/[token]/page.tsx`
  - `backend/app/services/report_service.py` (PDF report)
  - `backend/app/api/v1/clients.py` (comment/enforcement note)
- **`CLAUDE.md` edits:** update §4 (dimension table source + label); move
  "Automated Brand Authority/Content Quality scoring" off the §11 "do not build"
  list with a note that it shipped as *assisted, human-reviewed*.

## Testing

- **Service unit tests:** prompt builds correctly per dimension; JSON parse;
  retry-then-flag on failure; language-rule sanitization of bullets.
- **Endpoint tests:** generate → creates `suggested` row; accept (plain and
  adjusted) → writes `client.*`, recomputes GEO score, writes activity log.
- **Client-view test:** evidence bullets surface in the client-view payload, and
  `raw_narrative` never appears in any client-facing schema.

## Out of Scope (YAGNI)

- Auto-refresh / cadence-based regeneration (on-demand only in MVP).
- Hard-signal API integrations (Semrush backlinks, review-site scraping,
  Wikipedia/Wikidata lookups) — possible v2 hybrid engine.
- Per-signal ✓/partial/✗ rubric breakdown in the client view.
- Bulk "assess all clients" action.

## Success Criteria

1. Admin can generate a Claude-suggested score + evidence for each dimension
   on-demand, review it, and accept or adjust before it counts.
2. The accepted score flows into the existing GEO score with no formula change.
3. The client view shows 3–5 evidence bullets per dimension under the new label.
4. `raw_narrative` and other internal fields never reach any client-facing
   surface.
5. `SCORE_VERSION` bumped; label updated everywhere; CLAUDE.md reconciled.
