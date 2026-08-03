"""Scan-backed verification for published Outcome Actions."""
from dataclasses import dataclass
from datetime import datetime
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.outcome_action import OutcomeAction
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.outcome_action_service import (
    matching_query_result,
    source_query_result_for_action,
    transition_action,
)
from app.services import work_log_service


VERIFICATION_CLAIM = "Observed after publication; causality not established"


@dataclass(slots=True)
class VerificationSummary:
    verified: int = 0
    no_change: int = 0
    skipped_missing_identity: int = 0
    skipped_missing_query: int = 0
    rejected_scan: int = 0
    work_log_suggested: int = 0


class VerificationScanError(ValueError):
    """Raised when the requested verification scan does not belong to the client."""


def verify_waiting_actions(
    scan_id: uuid.UUID, client_id: uuid.UUID, db: Session
) -> VerificationSummary:
    """Verify client-owned published/waiting actions against one completed scan.

    The comparison is intentionally narrow: only actions tied to a concrete
    source ScanQueryResult are comparable. That prevents broad text matching
    from inventing proof where no stable query identity exists.
    """
    summary = VerificationSummary()
    scan = db.get(Scan, scan_id)
    if scan is None or scan.client_id != client_id:
        raise VerificationScanError("verification scan must belong to the client")
    if scan.status != "completed" or scan.completed_at is None:
        summary.rejected_scan = 1
        return summary

    actions = (
        db.query(OutcomeAction)
        .filter(
            OutcomeAction.client_id == client_id,
            OutcomeAction.status.in_(("published", "waiting_verification")),
        )
        .order_by(OutcomeAction.published_at, OutcomeAction.created_at)
        .all()
    )
    for action in actions:
        source_result = source_query_result_for_action(action, db)
        if source_result is None:
            summary.skipped_missing_identity += 1
            continue
        if not _is_after_publication(scan, action):
            summary.rejected_scan += 1
            continue

        after_result = matching_query_result(scan.id, source_result, db)
        if after_result is None:
            summary.skipped_missing_query += 1
            continue

        target_status = "verified" if after_result.brand_detected else "no_change"
        action.verification_result = _verification_evidence(scan, source_result, after_result)
        if action.status == "published":
            action.status = "waiting_verification"
        transition_action(action, target_status, db)
        if target_status == "verified":
            summary.verified += 1
            if work_log_service.suggest_verified_outcome_action(action, db) is not None:
                summary.work_log_suggested += 1
                db.refresh(action)
        else:
            summary.no_change += 1

    return summary


def _is_after_publication(scan: Scan, action: OutcomeAction) -> bool:
    if action.published_at is None:
        return False
    completed_at: datetime | None = scan.completed_at
    return completed_at is not None and completed_at > action.published_at


def _verification_evidence(
    scan: Scan, source_result: ScanQueryResult, result: ScanQueryResult
) -> dict[str, object]:
    return {
        "basis": "query_presence",
        "before_seen": bool(source_result.brand_detected),
        "after_seen": bool(result.brand_detected),
        "scan_id": str(scan.id),
        "claim": VERIFICATION_CLAIM,
    }
