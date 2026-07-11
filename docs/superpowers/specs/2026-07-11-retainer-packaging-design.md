# Retainer Packaging — Monthly Report v2 + Client Work Log — Design Spec

**Date:** 2026-07-11
**Status:** Approved design, pending implementation
**Phase:** 5 of the GEO end-to-end roadmap. Consumes Phases 1–4 output but every new
section degrades gracefully when its source phase has no data for a client — this
phase must be shippable even if a given client never used Phases 2–4.

## 1. Goal

Make the monthly deliverable *prove the retainer*. Today the report shows the score
and competitive picture; a RM4–5k/month client also needs to see **work delivered**:
technical fixes, content shipped, authority actions, citation growth, and
before/after AI answers. Two components:

1. **Monthly report v2** — five new sections in the existing WeasyPrint PDF.
2. **Client work log** — a curated, client-safe delivery timeline, visible on a new
   `/view/[token]/progress` tab and summarized in the PDF.

## 2. Non-goals

- No change to report generation/review flow: still auto-generated, Faris reviews
  before sending, 30-day cadence, R2 storage (CLAUDE.md §7, §8).
- No client login; the progress tab rides the existing share-token gate.
- No weekly digest changes.
- ActivityLog is NOT exposed to clients — it's an internal audit trail with internal
  vocabulary. The work log is a separate, whitelisted derivation (below).

## 3. Client work log

### 3.1 Why not just filter ActivityLog?

ActivityLog notes are written for the admin ("brand_authority assessment generated
(suggested 62)") and violate client-facing language rules. Rewriting history is worse
than deriving fresh. So: a new table whose rows are **born client-safe**.

### 3.2 Model

`backend/app/models/work_log_entry.py`:

```python
class WorkLogEntry(Base):
    __tablename__ = "work_log_entries"
    id          UUID pk
    client_id   UUID fk clients.id CASCADE, index
    category    String(32)   # technical | content | authority | visibility | correction
    description Text         # client-safe, sanitized at write time
    source      String(16)   # auto | manual
    source_ref  String(128) nullable  # "<event_type>:<entity id>" for dedupe of auto entries
    visible     Boolean default True  # admin can hide without deleting
    entry_date  Date         # when the work happened (editable for manual entries)
    created_at  datetime
```

Migration with RLS. Unique partial index on `(client_id, source_ref)` where source_ref
not null — auto-generation is idempotent.

### 3.3 Auto entries

A small `work_log_service.record(...)` is called at the same commit points that already
write ActivityLog, for this whitelist (mapping → client-safe template):

| Trigger (exists today / phase) | Category | Template |
|---|---|---|
| toolkit file verified (today) | technical | "Published and verified {file} so AI systems can read your site" |
| site audit run, N fixed since last (P2) | technical | "Technical AI-readiness check: {n} issues fixed since last audit" (only when n>0) |
| page audit re-run with score improvement (P3) | content | "Improved AI-readability of {url_path}: {old} → {new}" |
| deliverable reviewed (P3) | content | "Delivered: {title}" |
| authority asset → live/verified (P4) | authority | "Your {name} profile is now live" / "…verified" |
| remediation item corrected (today) | correction | "Corrected: {client-safe summary}" (reuse the item's existing client-facing text) |
| scan: query flipped to Seen by AI (Phase 1 diff data / scan_diff_service) | visibility | "Now seen by AI for: “{query_text}”" |

Every template passes through `language_sanitizer` at write time anyway (belt and
braces). Failures to write a work-log entry are best-effort: catch, rollback,
swallow — never undo the triggering operation (CLAUDE.md §10 workers rule applies
to this exactly).

**Manual entries:** Faris does plenty outside the app (a guest post, a directory
submission phone call). `POST` a manual entry with category + description + date.

### 3.4 API + admin UI

- `GET/POST /api/v1/clients/{id}/work-log`, `PATCH .../work-log/{id}` (edit
  description/visible/date — manual entries only editable; auto entries can only be
  hidden). Admin-only routes.
- Admin surface: a "Work log" card on `/clients/[id]/activity` (existing page, new
  section above the raw activity list) — add entry form + visibility toggles. No new
  admin nav page.

### 3.5 Client view tab

New public tab `/view/[token]/progress` (CLAUDE.md §9 public list updated):

- Timeline of visible entries grouped by month, category chips, newest first.
- Header stat row: "This month: N improvements" + per-category counts.
- Served by `client_view.py` via a whitelisted `WorkLogEntryPublic` schema
  (description, category, entry_date only — no ids beyond what rendering needs, no
  source/notes). Same uniform-404 token rules; the tab appears in the share-view nav
  only when ≥ 1 visible entry exists (no empty-state embarrassment for new clients).

## 4. Monthly report v2 — new sections

All built in `report_service` from data queried per report period (last 30 days,
same period logic the report already uses). **Every section renders only when it has
data; an empty phase yields no empty header.** Order in the PDF, after the existing
score/dimension pages:

1. **Work delivered this month** — the work log summary: per-category counts + up to
   10 visible entries. (Source: WorkLogEntry. Available immediately in this phase.)
2. **Technical health** — latest SiteAudit vs the last one before the period:
   passed/warned/failed counts, list of checks fixed this period. (Source: P2.)
3. **Content delivered** — reviewed ContentDeliverables + page-audit score
   improvements this period. (Source: P3.)
4. **Authority progress** — assets that became live/verified this period + review
   snapshot deltas ("Google rating 4.2 → 4.5"). (Source: P4.)
5. **AI sources trend** — client share-of-source over the period from Phase 1
   snapshots + flips won ("These sources now include you"). Language per the
   provenance feature: "sources AI answers drew from", never "cited". (Source: P1.)
6. **Before / after** — up to 3 queries that flipped to "Seen by AI" this period
   (scan_diff data), each rendered as the existing proof-card style: query, platform,
   verbatim snippet now vs "Not seen by AI" before. (Source: exists today +
   snippet/proof_card services.)

Implementation shape: extend `ReportData` with optional fields (all defaulting to
None/empty), one `_gather_*` helper per section inside `_gather_report_data`, one
`_build_*_html` per section — matching the existing structure exactly. Each gather
helper is wrapped so a failure in a new section can never block report generation
(log + skip section) — the known "silent report failure" bug class must not grow.

The Claude "what changed this month" narrative prompt gains the section summaries as
context (counts only, not full text) so the narrative can reference delivered work.
Generated once at build, persisted on the report — behavior unchanged.

## 5. Scorecard + share view coherence

- The existing `/view/[token]` overview gets one new line under the score: "N
  improvements delivered in the last 30 days" linking to the progress tab (only when
  n > 0).
- `generate_scorecard_pdf` (the one-pager) adds the same single line. No other
  scorecard changes.

## 6. Error handling

- Section gather failures: caught per-section, section skipped, structlog warning,
  report still builds and still goes to admin review.
- Work-log auto-writes: best-effort post-commit pattern (catch, rollback, swallow).
- Progress tab with a valid token but zero entries: tab hidden from nav; direct URL
  renders the overview-consistent empty state (not 404 — the token is valid).
- All new public schemas whitelisted in client_view; never raw internal fields
  (CLAUDE.md §8-9).

## 7. Testing

`test_work_log_service.py`:
1. Auto entry idempotence (same source_ref twice → one row).
2. Sanitizer applied (inject banned word into a template arg → cleaned).
3. Failure in work-log write doesn't roll back the triggering commit.
4. Manual entry CRUD; auto entries reject description edits, allow hide.

`test_report_v2.py`:
5. Client with all phases populated → all six sections present in HTML.
6. Client with nothing but a scan → v1-identical report, zero new headers, no error.
7. A gather helper raising → section absent, report builds, warning logged.
8. Period boundaries: entry dated outside the 30-day window excluded.

`test_client_view.py` additions:
9. Progress schema exposes exactly (description, category, entry_date); hidden
   entries absent; invalid token → uniform 404.
10. Overview improvement line present only when count > 0.

Banned-language grep across all new templates; seenby-verify; then a full
generate-review-send walkthrough with the demo client before calling it done.

## 8. Build order

1. Migration (work_log_entries, RLS).
2. work_log_service + auto hooks at existing commit points + tests.
3. Admin work-log card on the activity page + manual entry API.
4. Report v2 sections (gathers + HTML) + narrative context + tests.
5. Progress tab in client view + overview line + §9 update.
6. seenby-verify + end-to-end report walkthrough (seenby-demo-check).
