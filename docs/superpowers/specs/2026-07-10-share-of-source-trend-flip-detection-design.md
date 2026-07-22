# Share-of-Source Trend + Flip Detection — Design (v1)

**Date:** 2026-07-10
**Status:** Approved for planning
**Scope:** v1 — passive trend + auto-detected flip alerts, activity log only, no new admin UI actions

## 1. Summary

The [citation provenance / Share-of-Source design](2026-07-03-citation-provenance-share-of-source-design.md)
(shipped 2026-07-07) computes, from a client's latest completed scan, an
**acquisition list** — third-party pages that AI cites in response to the
client's own queries, where a competitor is mentioned and the client is not —
and **flip targets**, the top 3 of those pages ranked by citation count. It's
a single-snapshot, recompute-on-read view: every time the admin loads the
competitors page, it re-derives this from the latest scan only. There's no
memory of what the list looked like last month, and no signal when a flip
target actually gets earned.

This feature adds the missing time dimension: persist a snapshot of this
computation at every scan, so the admin can see the trend (is Share of
Source growing?) and get an automatic, verified signal the moment a
previously-absent client starts showing up on a page that used to cite only
a competitor — the "you got the mention" event that is the actual provable
outcome this category of work is judged on.

## 2. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Persistence trigger | **On-demand, scan-driven only** | No new scheduling. Snapshot is computed inline in the existing scan post-commit flow — stays inside the MVP's "scans are on-demand only" rule (CLAUDE.md §11). |
| What's persisted | **Full acquisition list, not just top-3 flip_targets** | A page ranked #4+ that later gets acquired should still register as a flip. Flip_targets stays a read-time `[:3]` slice, same as the live endpoint today. |
| Flip surfacing | **Activity log only** | Highest value-per-effort per user decision: no admin/Telegram alert channel, no "mark as pursued" workflow UI. Both can be added later without a redesign — flip-detection is already an isolated call site. |
| Flip-detection accuracy | **Verified only — skip domains that don't reappear** | If a previously-absent-client URL simply doesn't show up in the next scan's results (search drift), that's not logged as a flip. Only a confirmed "client now present at that exact URL" counts. Avoids false positives in the activity log. |
| Compute reuse | **Refactor, don't duplicate** | `compute_share_of_source`'s query + math is split into `_collect_sources` and `_summarize` helpers, shared by the existing live-read endpoint and the new snapshot writer. |
| Backfill | **None** | Snapshots start from the next scan forward. No retroactive snapshot generation for existing scan history. |

## 3. Non-goals (v1)

Explicitly out of scope for this spec — carried over from the broader GEO/AEO
service-gap discussion this feature came out of, so future work isn't assumed
to be covered by this ship:

- No digital-PR execution or outreach tooling — this tracks and detects wins,
  it does not help pursue them (no "mark as pursued" status field).
- No admin email/Telegram alert on flip (activity log only, v1).
- No monthly-PDF narrative integration (could feed `report_service`'s
  "what changed this month" narrative later; not this spec).
- No expansion beyond Perplexity — inherits the v1 scope of the underlying
  provenance feature.
- No general web-presence audit (directories, Reddit, Quora) — this only
  reflects domains that already surfaced in the client's own scan queries.
- No historical backfill of snapshots for scans that ran before this ships.

## 4. Data model

New table `share_of_source_snapshots` (new model file
`app/models/share_of_source_snapshot.py` + one Alembic migration):

| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `client_id` | FK → clients, indexed | |
| `scan_id` | FK → scans, unique | one snapshot per completed scan |
| `computed_at` | timestamp | |
| `total_third_party_sources` | int | denominator, for trend context |
| `client_share_pct` | float | the headline trend number |
| `competitor_shares` | JSON | `[{competitor_id, name, sources_present, share_pct}]` |
| `acquisition_list` | JSON | full list: `[{url, domain, title, citation_count, competitor_ids}]` |

## 5. Compute + write path

`provenance_service.py` is refactored (behavior-preserving for the existing
live endpoint) into:

- `_collect_sources(scan_id, client_id, db) -> dict[url, {domain, title, present}]`
  — the existing query against `ScanQuerySource`/`ScanQueryResult`, extracted
  as-is.
- `_summarize(unique, competitors, client) -> ShareOfSourceResponse`-shaped
  data — the existing pure math (share %, acquisition list, flip targets),
  extracted as-is.
- `compute_share_of_source(client_id, db)` (existing, unchanged signature/
  behavior) — calls both helpers against the latest completed scan, live,
  every read. No change to today's admin-facing behavior.
- `compute_and_persist_snapshot(scan_id, client_id, db)` (new) — calls
  `_collect_sources` and `_summarize` against the scan that just completed,
  persists a `ShareOfSourceSnapshot` row from the summary, and **keeps the
  `unique` dict from `_collect_sources` in memory** — flip detection (§6)
  needs raw per-URL client presence, not just the summarized acquisition
  list, so it must not be discarded after summarizing.

**Hook point:** `scan_service.run_scan`'s existing post-commit best-effort
block, immediately after `enrich_scan_sources` (snapshot data needs
enrichment's `present_brands` to already be populated):

```
alert_service...
provenance_service.enrich_scan_sources(scan.id, db)
provenance_service.compute_and_persist_snapshot(scan.id, client.id, db)   # NEW
action_center_service...
```

Each step keeps its own isolated try/except, matching the existing pattern —
a failure in the new step never touches the scan, `enrich_scan_sources`, or
`action_center_service`.

## 6. Flip detection

Runs inside `compute_and_persist_snapshot`, after the new snapshot row is
committed:

1. Load the client's previous snapshot (most recent one before this new
   row).
2. For each entry in the previous snapshot's `acquisition_list` (a URL where
   the client was absent, a competitor present), look up that same URL in
   the **new** scan's freshly-computed `unique` dict.
3. If the URL exists in the new data and now shows `client present = True`
   → log `ActivityLog(event_type="citation_flip", note="{domain} now cites
   {client.name} — previously only cited {competitor names}")`.
4. If the URL isn't present in the new scan's results at all, skip — not a
   verified flip, just search-result drift.

This is a second, inner try/except **after** the snapshot commit — a
flip-detection failure loses that run's activity-log entries but never
rolls back the already-persisted snapshot.

First scan for a client (no previous snapshot) → flip detection trivially
no-ops; snapshot still persists normally.

## 7. Read API

- `GET /clients/{client_id}/competitors/share-of-source` — **unchanged**,
  still recomputes live from the latest scan via `compute_share_of_source`.
  Zero behavior change, zero risk to the shipped feature.
- `GET /clients/{client_id}/competitors/share-of-source/history` — **new**,
  returns the last 12 snapshots as
  `[{computed_at, client_share_pct, total_third_party_sources}]`, ordered
  oldest→newest.

## 8. Frontend

Small trend sparkline added to the existing Share-of-Source section on
`/clients/[id]/competitors`, sourced from the new `/history` endpoint. Uses
this repo's `dataviz` skill conventions at implementation time. No new pages,
no new nav entries (CLAUDE.md §9 unaffected).

## 9. Error handling

- `compute_and_persist_snapshot` failure (persistence step) → log warning,
  return early. Nothing to diff against, so flip detection is skipped for
  that run.
- Flip-detection failure (after successful persistence) → log warning,
  swallow. Snapshot row still stands.
- Both are already inside the scan's post-commit best-effort envelope
  (catch + `db.rollback()` + swallow) per CLAUDE.md §10 — a failure here
  never undoes the scan itself.

## 10. Testing

Extends `backend/tests/test_provenance_share.py` (existing file, per the
seenby-workflow convention of extending rather than parallel-filing):

1. A completed scan persists a snapshot whose `client_share_pct` /
   `acquisition_list` matches what the live `compute_share_of_source` would
   return for that same scan.
2. Flip case: previous snapshot has URL X in `acquisition_list` (client
   absent, competitor present); new scan shows client present at URL X →
   asserts a `citation_flip` `ActivityLog` row is created.
3. No-flip case: URL X from the previous snapshot doesn't appear in the new
   scan at all → no activity log entry (guards the false-positive/noise
   case).
4. First-scan case: no previous snapshot → no error, snapshot still
   persists, zero flip entries.
5. Isolation case: force `compute_and_persist_snapshot` to raise → assert
   `scan_service.run_scan` still completes and commits normally (mirrors
   the existing `alert_service` failure-isolation test).
6. New `GET .../share-of-source/history` endpoint: ordering, limit,
   empty-history case.

Per the known trap already documented in `seenby-workflow`: scan-flow tests
must mock `enrich_scan_sources` and external API calls, following the
existing conftest pattern, to avoid live network calls / flakiness.
