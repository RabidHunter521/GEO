"""Scan-backed verification for published Outcome Actions."""
from dataclasses import dataclass
from datetime import datetime
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.outcome_action import OutcomeAction
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.outcome_action_service import transition_action
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
        source_result = _source_query_result(action, db)
        if source_result is None:
            summary.skipped_missing_identity += 1
            continue
        if source_result.scan_id == scan.id:
            summary.skipped_missing_query += 1
            continue
        if not _is_after_publication(scan, action):
            summary.rejected_scan += 1
            continue

        after_result = _matching_result(scan.id, source_result, db)
        if after_result is None:
            summary.skipped_missing_query += 1
            continue

        target_status = "verified" if after_result.brand_detected else "no_change"
        action.verification_result = _verification_evidence(scan, after_result)
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


def _source_query_result(action: OutcomeAction, db: Session) -> ScanQueryResult | None:
    source_id = _source_scan_query_result_id(action.source_ref)
    if source_id is None:
        return None
    result = db.get(ScanQueryResult, source_id)
    if result is None:
        return None
    source_scan = db.get(Scan, result.scan_id)
    if source_scan is None or source_scan.client_id != action.client_id:
        return None
    return result


def _source_scan_query_result_id(source_ref: str | None) -> uuid.UUID | None:
    if not source_ref:
        return None
    prefix, _, raw_id = source_ref.partition(":")
    if prefix not in {"scan_query_result", "scan_query_results"} or not raw_id:
        return None
    try:
        return uuid.UUID(raw_id)
    except ValueError:
        return None


def _matching_result(
    scan_id: uuid.UUID, source_result: ScanQueryResult, db: Session
) -> ScanQueryResult | None:
    return (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.platform == source_result.platform,
            ScanQueryResult.category == source_result.category,
            ScanQueryResult.query_text == source_result.query_text,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
        )
        .order_by(desc(ScanQueryResult.created_at), desc(ScanQueryResult.id))
        .first()
    )


def _is_after_publication(scan: Scan, action: OutcomeAction) -> bool:
    if action.published_at is None:
        return False
    completed_at: datetime | None = scan.completed_at
    return completed_at is not None and completed_at > action.published_at


def _verification_evidence(scan: Scan, result: ScanQueryResult) -> dict[str, object]:
    return {
        "basis": "query_presence",
        "before_seen": False,
        "after_seen": bool(result.brand_detected),
        "scan_id": str(scan.id),
        "claim": VERIFICATION_CLAIM,
    }
