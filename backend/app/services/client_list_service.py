from app.core.time import utcnow
"""Builds the enriched client list for the admin /clients overview.

Each client is decorated with its latest + previous GeoScore (for portfolio
score deltas) and the most recent Scan's status (so the dashboard can flag
failed or in-flight scans even when no score was produced).
"""
from datetime import datetime, timedelta
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.schemas.client import ClientListItem, ClientResponse


def compute_next_scan_due(last_scan_at: datetime | None, cadence_days: int) -> datetime | None:
    """Next-scan-due timestamp = last completed scan + cadence. None if never scanned."""
    if last_scan_at is None:
        return None
    return last_scan_at + timedelta(days=cadence_days)


def build_client_list(db: Session) -> list[ClientListItem]:
    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None))
        .order_by(desc(Client.created_at))
        .all()
    )
    if not clients:
        return []

    client_ids = [c.id for c in clients]

    # Two most recent geo scores per client via ROW_NUMBER — rn 1 is the
    # latest, rn 2 the previous (id breaks computed_at ties deterministically).
    score_rn = (
        func.row_number()
        .over(
            partition_by=GeoScore.client_id,
            order_by=(desc(GeoScore.computed_at), desc(GeoScore.id)),
        )
        .label("rn")
    )
    ranked_scores = (
        db.query(
            GeoScore.client_id.label("client_id"),
            GeoScore.overall_score.label("overall_score"),
            GeoScore.computed_at.label("computed_at"),
            score_rn,
        )
        .filter(GeoScore.client_id.in_(client_ids))
        .subquery()
    )
    score_rows = (
        db.query(ranked_scores).filter(ranked_scores.c.rn <= 2).all()
    )
    latest_score_by_client = {r.client_id: r for r in score_rows if r.rn == 1}
    previous_score_by_client = {r.client_id: r for r in score_rows if r.rn == 2}

    # Most recent scan per client (any status) for the dashboard status flag.
    scan_rn = (
        func.row_number()
        .over(
            partition_by=Scan.client_id,
            order_by=(desc(Scan.triggered_at), desc(Scan.id)),
        )
        .label("rn")
    )
    ranked_scans = (
        db.query(
            Scan.client_id.label("client_id"),
            Scan.status.label("status"),
            Scan.triggered_at.label("triggered_at"),
            scan_rn,
        )
        .filter(Scan.client_id.in_(client_ids))
        .subquery()
    )
    scan_rows = db.query(ranked_scans).filter(ranked_scans.c.rn == 1).all()
    latest_scan_by_client = {r.client_id: r for r in scan_rows}

    items = []
    for c in clients:
        latest = latest_score_by_client.get(c.id)
        previous = previous_score_by_client.get(c.id)
        latest_scan = latest_scan_by_client.get(c.id)
        last_scan_at = latest.computed_at if latest else None
        # Prospects run on ad-hoc outreach scans, not a review cadence — don't
        # surface "scan overdue" reminders for them in the portfolio overview.
        next_due = (
            None if c.is_prospect else compute_next_scan_due(last_scan_at, c.scan_cadence_days)
        )
        base = ClientResponse.model_validate(c).model_dump()
        items.append(
            ClientListItem(
                **base,
                latest_overall_score=latest.overall_score if latest else None,
                last_scan_at=last_scan_at,
                previous_overall_score=previous.overall_score if previous else None,
                latest_scan_status=latest_scan.status if latest_scan else None,
                latest_scan_triggered_at=latest_scan.triggered_at if latest_scan else None,
                next_scan_due=next_due,
                is_scan_overdue=bool(next_due and next_due < utcnow()),
            )
        )
    return items
