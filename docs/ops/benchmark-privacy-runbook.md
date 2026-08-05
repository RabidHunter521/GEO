# Benchmark Privacy Runbook (Phase 6)

Operating guide for the cohort benchmark engine and the SEA AI Visibility
Index. Read this before generating, approving, publishing, or withdrawing
anything, and before changing any threshold.

**The one-line rule:** when a number cannot be published safely, the answer is
always suppression. It is never a lowered threshold.

---

## 1. What exists

| Table | Holds | Exposure |
|---|---|---|
| `benchmark_cohorts` | Versioned definitions of who is comparable | Never client-facing |
| `benchmark_cohort_memberships` | **Which clients counted, and why the rest did not** | **Never leaves the backend** |
| `benchmark_snapshots` | Immutable aggregate results | Only via banded comparison schemas |
| `benchmark_publications` | Reviewed index editions | Published payload only, via one anonymous route |

All four have RLS enabled with zero policies and `anon` revoked, per CLAUDE.md
§8. RLS is defence in depth here, not the active control — the active control
is that only `postgres` connects.

`benchmark_cohort_memberships` is the only table in Phase 6 that maps an
aggregate back to identifiable organisations. It exists for operator
explainability and audit. If you ever find it reachable from a client or public
schema, that is an incident, not a bug.

---

## 2. Thresholds and where they are enforced

| Rule | Value | Enforced by |
|---|---|---|
| Minimum cohort size | 10 organisations | `MIN_COHORT_MEMBER_FLOOR` + `CHECK ck_benchmark_cohorts_min_member_count_floor` |
| Minimum metric contributors | 5 | `MIN_METRIC_CONTRIBUTORS`, snapshot generation |
| Differencing gap between nested cohorts | ≥ 5 contributors | `generate_ladder_snapshots` |
| Single-client dominance in market intelligence | ≤ 20% of observations | `MAX_SINGLE_CLIENT_SHARE` |
| Minimum query coverage to be eligible | 10 tracked queries | `BENCHMARK_MIN_COVERAGE` |
| Measurement staleness | 45 days from period end | `BENCHMARK_MAX_STALENESS_DAYS` |

**Configurable upward only.** The 10-organisation floor is a database CHECK
precisely so it cannot be lowered by configuration. Lowering it is the single
change that would silently convert every correct suppression into a publishable
number. If a market is too small, it stays suppressed until it grows.

Changing any threshold means minting a new `definition_version` (cohorts) or
`calculation_version` (snapshots). Never edit thresholds in place — a published
figure must always be traceable to the exact rules that produced it.

---

## 3. Suppression reasons and what they mean

| Reason | Meaning |
|---|---|
| `cohort_below_minimum` | Fewer than 10 eligible organisations |
| `insufficient_contributors` | Cohort is big enough; too few have this metric |
| `differencing_risk` | A nested cohort is close enough that subtraction would expose the difference group |
| `no_cohort` | No approved snapshot on this client's ladder |
| `no_client_value` | The cohort published, but this client has no reading |
| `not_eligible` | The client itself is excluded — see exclusion codes |

Exclusion codes on membership rows: `opted_out`, `archived`, `prospect`,
`no_industry_pack`, `unmappable_country`, `unknown_scale`,
`insufficient_coverage`, `stale_measurement`,
`unsupported_measurement_version`.

Every exclusion carries a reason and every inclusion carries none — both
directions are CHECK constraints. An unexplainable exclusion is
indistinguishable from a bug.

---

## 4. Opt-out handling

Set `clients.benchmark_opt_out = true`. The client then stops contributing to
peer aggregates **and** stops receiving comparisons.

**Opt-out is forward-looking, and must be described that way.** It does not
retroactively rewrite an already-approved snapshot: that aggregate describes a
period the client genuinely was a member of, and mutating it would change a
figure someone may already have been shown. Opt-out removes the client from
cohorts computed *after* the flag is set.

If a client demands retroactive removal, the correct response is to withdraw
the affected publications (§7), not to edit snapshots. Editing is blocked by a
trigger anyway.

---

## 5. Generating snapshots

Monthly, after the period closes:

```
workers.tasks.benchmark_tasks.generate_monthly_benchmarks
```

Never mid-period — a partial month compared against complete ones reads as a
collapse in performance when it is only a collapse in elapsed time.

Reruns are safe. The same `calculation_version` updates its own unapproved row
in place and **refuses to touch an approved one**. A logic change requires a new
`calculation_version`, which writes a second row rather than overwriting the
first.

---

## 6. Snapshot immutability

Approved snapshots cannot be updated or deleted. Enforced twice:

- plpgsql trigger `reject_approved_benchmark_snapshot_change` (covers every
  writer that can reach the table);
- an ORM guard in `app/models/benchmark_snapshot.py` (covers application
  writes, raises a domain error, and is testable on SQLite).

Both read the same `approved_at` value so they cannot drift.

Corrections create a new calculation version or a replacement snapshot. They
never mutate a published value.

---

## 7. Publication workflow

```
POST /api/v1/benchmarks/publications                 → draft
POST /api/v1/benchmarks/publications/{id}/approve    → approved  (different actor)
POST /api/v1/benchmarks/publications/{id}/publish    → published
POST /api/v1/benchmarks/publications/{id}/withdraw   → withdrawn
GET  /api/v1/public/benchmarks/{slug}                → anonymous read
```

**Separation of duty is procedural, not authentication.** There is one shared
admin API key and `require_api_key` carries no actor identity, so the approver
is named explicitly in the request and the service and a CHECK constraint both
refuse an approval matching `generated_by`. Do not describe this to anyone as
an access control.

**Publishing never recalculates.** It promotes the reviewed payload after
verifying it against its SHA-256. If approval and publication disagreed, the
reviewer would have approved one set of numbers while the world received
another.

Approval re-derives the draft and compares hashes. If the underlying data moved
(a cohort retired, a new snapshot approved), approval is refused and the draft
must be regenerated and read again.

### Withdrawal / incident response

1. `POST .../withdraw` with a reason. Public access closes on the next request.
2. The row is **not deleted** — a withdrawn edition was public and has to remain
   answerable for.
3. If the withdrawal is due to a data defect, fix the defect, generate a new
   `calculation_version`, and issue a new edition. Never re-approve the old one;
   approved content is frozen.

---

## 8. What is never published

- client IDs, names, domains, locations, or query text;
- exact member counts (bands only: `10–19`, `20–49`, `50–99`, `100+`);
- exact ranks (bands only: bottom quartile / middle half / top quartile);
- market-area (city) cuts in the public index — country level only;
- estimated revenue or any modelled money figure;
- any metric that does not clear the gates in all three packs.

---

## 9. Release gate

Run before shipping any Phase 6 change.

### Automated (runnable here)

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q
cd backend && .venv/Scripts/python.exe -m ruff check app workers tests
cd frontend && npx vitest run --project unit
cd frontend && npm run typecheck && npm run build
git diff --check
```

### Requires a real Postgres — NOT runnable from this workspace

`backend/.env` points at production Supabase, so none of the following may be
run locally. Execute them in CI's throwaway Postgres or a scratch database.

1. **Migration reversibility.** `alembic upgrade head`, `alembic downgrade
   a4b5c6d7e8f9`, `alembic upgrade head`. CI's `migrations` job already runs
   `downgrade base` and re-upgrades on every push.
2. **RLS coverage.** CI's "Every table must have RLS enabled" job checks
   `relrowsecurity` across all tables. Confirm the four Phase 6 tables appear.
3. **Cross-tenant denial.** With a non-owner and an anonymous role, attempt
   `SELECT` on each of the four tables. All must be denied.
4. **Query plans.** `EXPLAIN (ANALYZE, BUFFERS)` on cohort eligibility,
   snapshot lookup, and client comparison. Confirm the three Phase 6 indexes
   are used before adding any more.
5. **Job recovery.** Interrupt `generate_monthly_benchmarks` mid-run and rerun
   it. Confirm idempotency and that an approved snapshot is untouched.

### Requires a browser — NOT runnable from this workspace

6. **Three-pack acceptance.** Generate eligible or correctly suppressed cohorts
   for healthcare, F&B and local services; view one client comparison on
   `/benchmarks` and on a share link; approve and publish one synthetic edition;
   withdraw it; confirm public access closes without deleting the audit record.
7. **Accessibility.** Keyboard traversal and 360px layout on `/benchmarks` and
   the client benchmark card. These are implemented but have **no automated
   coverage** — the repo has no DOM test environment — so this check is the
   only thing standing behind them.

---

## 10. Rollback

Phase 6 is additive. To roll back:

```
alembic downgrade a4b5c6d7e8f9
```

This drops `benchmark_publications`, `benchmark_snapshots`,
`benchmark_cohort_memberships`, `benchmark_cohorts`, and
`clients.benchmark_opt_out`, and removes the immutability trigger and function.

Downgrade drops snapshots before cohorts deliberately: `snapshots.cohort_id` is
`RESTRICT`, so the reverse order fails on a populated database.

**Rolling back destroys the aggregate history and the membership audit trail.**
Export both first if there is any chance of needing to explain a published
figure afterwards.

---

## 11. Retention

- Membership rows are the audit trail for who counted; keep them as long as the
  snapshots they explain.
- Withdrawn publications are kept indefinitely. They were public.
- Snapshots are immutable once approved and are not purged by the 90-day raw
  response retention rule — they contain no raw responses.
