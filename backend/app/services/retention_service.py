# backend/app/services/retention_service.py
"""Data-retention housekeeping (CLAUDE.md §8).

- Raw scan responses are nulled 90 days after capture. Detection flags
  (brand_detected, recommendation_position) are kept — they are "purge-proof"
  and keep powering competitor intelligence / win-loss after the text is gone.
- Clients are hard-deleted 6 months after they are archived (churned). Child
  rows cascade via the FK ondelete=CASCADE on every child table.
"""
from datetime import datetime, timedelta

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.constants import CHURN_DELETE_DAYS, RAW_RESPONSE_RETENTION_DAYS
from app.models.client import Client
from app.models.scan_query_result import ScanQueryResult

logger = structlog.get_logger()


def purge_raw_responses(db: Session) -> int:
    """Null out response_text on scan results past the retention window.

    Returns the number of rows updated. created_at is stored as naive UTC, so
    the threshold is naive UTC to match.
    """
    threshold = datetime.utcnow() - timedelta(days=RAW_RESPONSE_RETENTION_DAYS)
    result = db.execute(
        update(ScanQueryResult)
        .where(
            ScanQueryResult.created_at < threshold,
            ScanQueryResult.response_text.isnot(None),
        )
        .values(response_text=None)
    )
    db.commit()
    count = result.rowcount or 0
    logger.info(
        "raw_responses_purged",
        count=count,
        older_than_days=RAW_RESPONSE_RETENTION_DAYS,
    )
    return count


def delete_churned_clients(db: Session) -> int:
    """Hard-delete clients archived longer than the churn window.

    Deleting the parent triggers ON DELETE CASCADE for scans, scan results,
    geo scores, competitors, reports, activity, etc. Returns the count deleted.
    """
    threshold = datetime.utcnow() - timedelta(days=CHURN_DELETE_DAYS)
    clients = (
        db.query(Client)
        .filter(Client.archived_at.isnot(None), Client.archived_at < threshold)
        .all()
    )
    count = 0
    for client in clients:
        logger.info("churned_client_deleting", client_id=str(client.id))
        db.delete(client)
        count += 1
    db.commit()
    logger.info(
        "churned_clients_deleted",
        count=count,
        older_than_days=CHURN_DELETE_DAYS,
    )
    return count
