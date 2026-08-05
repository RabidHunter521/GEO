"""Scheduled generation of benchmark snapshots after a period closes.

Thin entrypoint per CLAUDE.md section 10: opens a session and delegates to
`benchmark_snapshot_service`. All aggregation, suppression, and privacy logic
lives in the service so it is testable without Celery.

Runs after period close, never during one — a snapshot taken mid-period would
compare a partial month against complete ones. Reruns are safe: the same
calculation version updates its own unapproved row in place and refuses to
touch an approved one, so a retry cannot fork a published number.
"""
from datetime import date

import structlog

from app.core.database import SessionLocal
from app.services.benchmark_cohort_service import eligible_members_for_period
from app.services.benchmark_period import previous_month_bounds
from app.services.benchmark_snapshot_service import (
    BENCHMARK_METRICS,
    generate_ladder_snapshots,
    get_or_create_cohort,
    record_membership,
)
from workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.benchmark_tasks.generate_monthly_benchmarks")
def generate_monthly_benchmarks(period_start: str | None = None, period_end: str | None = None):
    """Build every cohort snapshot for a closed month.

    Explicit dates are accepted so a period can be regenerated deliberately;
    the default is the previous calendar month.
    """
    if period_start and period_end:
        start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
    else:
        start, end = previous_month_bounds(date.today())

    logger.info("benchmark_generation_start", period_start=str(start), period_end=str(end))
    db = SessionLocal()
    try:
        everyone = eligible_members_for_period(db, start, end, include_excluded=True)
        included = [member for member in everyone if member.eligible]

        # One membership audit row per client per cohort the client belongs to,
        # including the exclusions and their reasons.
        cohort_specs = {member.spec.cohort_key: member.spec for member in included}
        for spec in cohort_specs.values():
            record_membership(db, get_or_create_cohort(db, spec), everyone, start, end)

        written = 0
        for spec in cohort_specs.values():
            for metric_key in BENCHMARK_METRICS:
                generate_ladder_snapshots(db, spec, included, metric_key, start, end)
                written += 1

        logger.info(
            "benchmark_generation_complete",
            period_start=str(start),
            period_end=str(end),
            cohort_count=len(cohort_specs),
            metric_runs=written,
            eligible_clients=len(included),
        )
        return {"cohorts": len(cohort_specs), "metric_runs": written}
    finally:
        db.close()
