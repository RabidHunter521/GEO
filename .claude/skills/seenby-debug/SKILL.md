---
name: seenby-debug
description: Systematic debugging paths for SeenBy — scan failures, Celery/worker issues, LLM output problems, score discrepancies, email/report failures. Trigger on any bug report, "scan failed", "score looks wrong", "email didn't send", "report is broken", "why is this empty", before proposing any fix. Encodes where evidence lives so diagnosis starts from data, not guesses.
---

# SeenBy Debugging Paths

Rule zero: reproduce or locate evidence BEFORE proposing a fix (superpowers:systematic-debugging applies). Every subsystem below logs somewhere — start there.

## Where evidence lives

| Symptom area | Look first |
|---|---|
| Scan behavior | `activity_log` rows for the client; structlog output of the worker; `scans` + `scan_query_results` rows |
| LLM output quality/cost | `llm_call_log` rows (service name + prompt version + tokens); prompt registry version |
| Platform failures | scan marked platform unavailable + activity log entry; `PlatformResult` retry path in `platform_clients/base.py` |
| Score discrepancies | `scoring_service.py` + `SCORE_WEIGHTS`/`SCORE_BANDS` in constants; GeoScore rows; check SCORE_VERSION |
| Emails/digest | `email_service.py` structlog; digest is best-effort — check it didn't swallow an exception |
| Reports/PDF | report rows; WeasyPrint errors in worker logs; R2 upload path |
| Share view 404s | token valid? client archived? share link revoked? — uniform 404 is BY DESIGN for all three |

## Known failure modes (check before deep-diving)

1. **Scan "stuck"**: pending/running scans older than `ACTIVE_SCAN_STALE_MINUTES` (15) are treated as dead — a crashed worker, not a hang.
2. **One platform down ≠ scan failed**: score computes from remaining platforms; platform marked unavailable. If the score moved oddly, check whether a platform dropped out (AI Citability = equal-weighted average of ENABLED+AVAILABLE platforms only).
3. **LLM feature returns nothing**: services return None on unparseable output by design. Check `llm_call_log` for the call, then whether `stop_reason == "max_tokens"` (truncated JSON) or the model added code fences.
4. **Fractional score band bugs**: bands are integer ranges; always go through `get_score_band()` / `getScoreColor()` — a 79.5 handled ad hoc falls through bands.
5. **Empty local queries**: clients with no city/state/country get NO recommendation/local queries by design — not a bug; scan count will be lower.
6. **Tests flaking with network calls**: scan-flow tests must mock `enrich_scan_sources` and all platform/LLM clients — see `test_api_provenance.py` conftest patterns.
7. **"Works locally, broken in prod"**: check whether an Alembic migration was ever applied to Supabase — the repo has a history of locally-verified-only migrations.
8. **Digest/alert side effects**: post-commit best-effort blocks catch + rollback + swallow. A missing alert is likely a swallowed exception — check logs, not the scan result.

## Method

1. State the symptom precisely (which client, which surface, when).
2. Pull the evidence rows/logs above. Paste the actual data into your reasoning.
3. Form ONE hypothesis that explains ALL the evidence; predict what else would be true; check that.
4. Only then edit code — with a failing test that reproduces the bug first.
5. `seenby-verify` before claiming fixed. If the bug was client-visible, also check the demo path (`seenby-demo-check`).
