"""Scan-to-scan diff — what changed between the two most recent completed scans.

Compares the client's own query results (competitor_id IS NULL) matched by
(platform, category, query_text). Uses only persisted brand_detected flags, so
it survives the 90-day raw-response purge.
"""
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.scan import ScanDiffQuery, ScanDiffResponse


def _visibility(results: list[ScanQueryResult]) -> float | None:
    if not results:
        return None
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def compute_scan_diff(client_id: uuid.UUID, db: Session) -> ScanDiffResponse:
    scans = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .limit(2)
        .all()
    )
    if not scans:
        return ScanDiffResponse()

    latest = scans[0]
    previous = scans[1] if len(scans) > 1 else None

    def own_results(scan_id):
        # Exclude hallucination-flagged rows — consistent with win_loss_service;
        # a flagged response's brand_detected is unreliable and would surface
        # spurious changes in the diff.
        return (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == scan_id,
                ScanQueryResult.competitor_id.is_(None),
                ScanQueryResult.hallucination_flagged.is_(False),
            )
            .all()
        )

    latest_results = own_results(latest.id)

    if previous is None:
        return ScanDiffResponse(
            latest_scan_id=latest.id,
            latest_scan_at=latest.completed_at,
            latest_visibility=_visibility(latest_results),
            has_comparison=False,
        )

    previous_results = own_results(previous.id)
    prev_by_key = {
        (r.platform, r.category, r.query_text): r.brand_detected for r in previous_results
    }

    newly_seen: list[ScanDiffQuery] = []
    newly_unseen: list[ScanDiffQuery] = []
    for r in latest_results:
        key = (r.platform, r.category, r.query_text)
        if key not in prev_by_key:
            continue
        was = prev_by_key[key]
        if r.brand_detected and not was:
            newly_seen.append(ScanDiffQuery(platform=r.platform, category=r.category, query_text=r.query_text))
        elif not r.brand_detected and was:
            newly_unseen.append(ScanDiffQuery(platform=r.platform, category=r.category, query_text=r.query_text))

    return ScanDiffResponse(
        latest_scan_id=latest.id,
        previous_scan_id=previous.id,
        latest_scan_at=latest.completed_at,
        previous_scan_at=previous.completed_at,
        latest_visibility=_visibility(latest_results),
        previous_visibility=_visibility(previous_results),
        newly_seen=newly_seen,
        newly_unseen=newly_unseen,
        has_comparison=True,
    )
