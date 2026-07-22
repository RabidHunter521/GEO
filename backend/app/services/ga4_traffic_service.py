"""GA4 AI-referral traffic sync. Pure classification/aggregation here is
unit-tested without Google; the API call itself is isolated in _fetch_rows so
tests mock exactly one seam."""
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy.orm import Session

from app.core.constants import AI_REFERRER_DOMAINS
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.models.client import Client

logger = structlog.get_logger()


def classify_referrer(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain, label in AI_REFERRER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return None


def _canonical_domain(source: str) -> str | None:
    host = (source or "").strip().lower()
    for domain in AI_REFERRER_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


def aggregate_rows(rows: list[tuple[str, str, int]]) -> dict[date, dict]:
    out: dict[date, dict] = {}
    for yyyymm, source, sessions in rows:
        domain = _canonical_domain(source)
        if domain is None:
            continue
        period = date(int(yyyymm[:4]), int(yyyymm[4:6]), 1)
        bucket = out.setdefault(period, {"ai_visitors": 0, "breakdown": {}})
        bucket["ai_visitors"] += sessions
        bucket["breakdown"][domain] = bucket["breakdown"].get(domain, 0) + sessions
    return out


class Ga4SyncError(Exception):
    pass


@dataclass
class SyncReport:
    synced_periods: list[date] = field(default_factory=list)
    skipped_manual: list[date] = field(default_factory=list)
    error: str | None = None


def _fetch_rows(property_id: str, months_back: int) -> list[tuple[str, str, int]]:
    """The single Google seam. Report: dimensions yearMonth + sessionSource,
    metric sessions, date range = first day of (current month - months_back)
    to today. Raises Ga4SyncError on any API/auth failure.

    API shapes verified against the GA4 Data API v1beta docs (context7,
    2026-07-22): BetaAnalyticsDataClient.run_report(RunReportRequest) with
    response.rows[*].dimension_values / metric_values."""
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange, Dimension, Metric, RunReportRequest,
        )
        from google.oauth2 import service_account

        creds_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON")
        if not creds_json:
            raise Ga4SyncError("GA4_SERVICE_ACCOUNT_JSON is not configured")
        creds = service_account.Credentials.from_service_account_info(json.loads(creds_json))
        client = BetaAnalyticsDataClient(credentials=creds)

        today = date.today()
        start_month = today.month - months_back
        start_year = today.year
        while start_month < 1:
            start_month += 12
            start_year -= 1
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name="yearMonth"), Dimension(name="sessionSource")],
            metrics=[Metric(name="sessions")],
            date_ranges=[DateRange(start_date=f"{start_year}-{start_month:02d}-01",
                                   end_date=today.isoformat())],
        )
        response = client.run_report(request)
        return [
            (row.dimension_values[0].value, row.dimension_values[1].value,
             int(row.metric_values[0].value))
            for row in response.rows
        ]
    except Ga4SyncError:
        raise
    except Exception as exc:  # auth, quota, network — one seam, one error type
        raise Ga4SyncError(str(exc)) from exc


def sync_client_traffic(client_id: uuid.UUID, db: Session, months_back: int = 2) -> SyncReport:
    client = db.get(Client, client_id)
    if client is None or not client.ga4_property_id:
        return SyncReport(error="GA4 property not configured for this client")
    try:
        rows = _fetch_rows(client.ga4_property_id, months_back)
    except Ga4SyncError as exc:
        logger.error("ga4_sync_failed", client_id=str(client_id), error=str(exc))
        return SyncReport(error=str(exc))

    report = SyncReport()
    for period, data in sorted(aggregate_rows(rows).items()):
        existing = (
            db.query(AiTrafficSnapshot)
            .filter(AiTrafficSnapshot.client_id == client_id,
                    AiTrafficSnapshot.period == period)
            .first()
        )
        if existing is not None and existing.source == "manual":
            report.skipped_manual.append(period)
            continue
        if existing is None:
            existing = AiTrafficSnapshot(client_id=client_id, period=period)
            db.add(existing)
        existing.ai_visitors = data["ai_visitors"]
        existing.breakdown = data["breakdown"]
        existing.source = "ga4"
        report.synced_periods.append(period)
    db.commit()
    logger.info("ga4_sync_done", client_id=str(client_id),
                synced=len(report.synced_periods), skipped=len(report.skipped_manual))
    return report
