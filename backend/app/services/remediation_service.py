# backend/app/services/remediation_service.py
"""Remediation loop — the "Flagged -> In progress -> Corrected" lifecycle the
SeenBy team works through for AI hallucinations and competitor-won queries.

Why this exists: ScanQueryResult.hallucination_flagged is a per-scan boolean that
resets every scan, and content gaps aren't stored at all (they're derived live in
win_loss_service). Neither can show a client *progress over time*. RemediationItem
persists the state, and this service keeps it in sync with the latest scan:

  - a newly flagged hallucination / newly lost query  -> created as "flagged"
  - an item that re-appears after being corrected      -> reopened to "flagged"
  - an item no longer present in the latest scan        -> auto "corrected"

Status can also be advanced manually by the admin (e.g. -> "in_progress").
Everything here is best-effort: a failure must never corrupt scan state.
"""
import uuid
from datetime import datetime

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import REMEDIATION_STATUSES
from app.models.remediation_item import RemediationItem
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.win_loss_service import compute_win_loss

logger = structlog.get_logger()


def _current_hallucination_keys(client_id: uuid.UUID, db: Session) -> dict[tuple[str, str], str | None]:
    """{(platform, query_text): None} for admin-flagged hallucinations in the latest scan."""
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return {}
    rows = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.hallucination_flagged.is_(True),
        )
        .all()
    )
    return {(r.platform, r.query_text): None for r in rows}


def _current_content_gap_keys(client_id: uuid.UUID, db: Session) -> dict[tuple[str, str], str | None]:
    """{(platform, query_text): "Competitor A, Competitor B"} for queries a competitor
    was seen for and the client was not (win/loss 'lost' outcomes)."""
    win_loss = compute_win_loss(client_id, db)
    keys: dict[tuple[str, str], str | None] = {}
    for entry in win_loss.entries:
        if entry.outcome == "lost":
            detail = ", ".join(entry.competitors_seen) or None
            keys[(entry.platform, entry.query_text)] = detail
    return keys


def _sync_type(
    db: Session,
    client_id: uuid.UUID,
    item_type: str,
    current: dict[tuple[str, str], str | None],
    now: datetime,
) -> None:
    existing = {
        (i.platform, i.label): i
        for i in db.query(RemediationItem)
        .filter(RemediationItem.client_id == client_id, RemediationItem.item_type == item_type)
        .all()
    }

    # Present now -> create (flagged) or refresh; reopen if it had been corrected.
    for (platform, label), detail in current.items():
        item = existing.get((platform, label))
        if item is None:
            db.add(RemediationItem(
                client_id=client_id,
                item_type=item_type,
                platform=platform,
                label=label,
                detail=detail,
                status="flagged",
                first_seen_at=now,
            ))
        else:
            item.detail = detail
            if item.status == "corrected":
                # The problem came back after we'd fixed it — reopen the loop.
                item.status = "flagged"
                item.resolved_at = None

    # Absent now -> the latest scan no longer shows it: auto-corrected.
    for (platform, label), item in existing.items():
        if (platform, label) not in current and item.status != "corrected":
            item.status = "corrected"
            item.resolved_at = now


def sync_remediation_items(client_id: uuid.UUID, db: Session) -> None:
    """Reconcile a client's remediation items with the latest scan. Commits.
    Best-effort: rolls back and logs on any failure, never raises."""
    try:
        now = datetime.utcnow()
        _sync_type(db, client_id, "hallucination", _current_hallucination_keys(client_id, db), now)
        _sync_type(db, client_id, "content_gap", _current_content_gap_keys(client_id, db), now)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("remediation_sync_failed", client_id=str(client_id), error=str(exc))


# Active items first (flagged, then in_progress), most recently corrected last.
_STATUS_ORDER = {"flagged": 0, "in_progress": 1, "corrected": 2}


def get_remediation_items(
    client_id: uuid.UUID, db: Session, include_corrected: bool = True
) -> list[RemediationItem]:
    items = (
        db.query(RemediationItem)
        .filter(RemediationItem.client_id == client_id)
        .all()
    )
    if not include_corrected:
        items = [i for i in items if i.status != "corrected"]
    # flagged/in_progress by first seen (oldest pain first); corrected by most
    # recently resolved (freshest wins on top of the corrected group).
    return sorted(
        items,
        key=lambda i: (
            _STATUS_ORDER.get(i.status, 0),
            (i.resolved_at or i.first_seen_at)
            if i.status == "corrected"
            else i.first_seen_at,
        ),
        reverse=False,
    )


def set_remediation_status(item_id: uuid.UUID, status: str, db: Session) -> RemediationItem | None:
    """Admin status override. Sets/clears resolved_at to match. Returns None if not found."""
    if status not in REMEDIATION_STATUSES:
        raise ValueError(f"Invalid remediation status: {status}")
    item = db.get(RemediationItem, item_id)
    if item is None:
        return None
    item.status = status
    item.resolved_at = datetime.utcnow() if status == "corrected" else None
    db.commit()
    db.refresh(item)
    return item
