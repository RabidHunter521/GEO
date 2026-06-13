import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.competitor import Competitor
from app.schemas.scan import (
    TriggerScanRequest,
    ScanResponse,
    ScanQueryResultResponse,
    ScanWithResultsResponse,
)

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post(
    "/",
    response_model=ScanResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
def trigger_scan(payload: TriggerScanRequest, db: Session = Depends(get_db)):
    from workers.tasks.scan_tasks import execute_scan
    from app.models.client import Client
    from app.services.scan_service import has_active_scan
    client = db.get(Client, payload.client_id)
    if not client or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    if has_active_scan(payload.client_id, db):
        raise HTTPException(status_code=409, detail="Scan already in progress")
    from app.core.constants import SCAN_PLATFORM_MULTI
    scan = Scan(client_id=payload.client_id, platform=SCAN_PLATFORM_MULTI)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    execute_scan.delay(str(scan.id))
    return scan


@router.get(
    "/client/{client_id}/latest",
    response_model=ScanWithResultsResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_scan(client_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id)
        .order_by(Scan.triggered_at.desc())
        .first()
    )
    if not scan:
        return None

    if scan.status != "completed":
        return ScanWithResultsResponse(
            id=scan.id,
            client_id=scan.client_id,
            platform=scan.platform,
            status=scan.status,
            triggered_at=scan.triggered_at,
            completed_at=scan.completed_at,
            results=[],
        )

    rows = (
        db.query(ScanQueryResult, Competitor.name.label("competitor_name"))
        .outerjoin(Competitor, ScanQueryResult.competitor_id == Competitor.id)
        .filter(ScanQueryResult.scan_id == scan.id)
        .all()
    )
    results = [
        ScanQueryResultResponse(
            id=row.ScanQueryResult.id,
            scan_id=row.ScanQueryResult.scan_id,
            platform=row.ScanQueryResult.platform,
            competitor_id=row.ScanQueryResult.competitor_id,
            competitor_name=row.competitor_name,
            category=row.ScanQueryResult.category,
            query_text=row.ScanQueryResult.query_text,
            response_text=row.ScanQueryResult.response_text,
            brand_detected=row.ScanQueryResult.brand_detected,
            hallucination_flagged=row.ScanQueryResult.hallucination_flagged,
            recommendation_position=row.ScanQueryResult.recommendation_position,
            created_at=row.ScanQueryResult.created_at,
        )
        for row in rows
    ]
    return ScanWithResultsResponse(
        id=scan.id,
        client_id=scan.client_id,
        platform=scan.platform,
        status=scan.status,
        triggered_at=scan.triggered_at,
        completed_at=scan.completed_at,
        results=results,
    )


@router.get(
    "/{scan_id}",
    response_model=ScanResponse,
    dependencies=[Depends(require_api_key)],
)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.post(
    "/{scan_id}/results/{result_id}/flag-hallucination",
    dependencies=[Depends(require_api_key)],
)
def flag_hallucination_result(
    scan_id: uuid.UUID,
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    from app.services.alert_service import flag_hallucination
    try:
        flag_hallucination(result_id, db, expected_scan_id=scan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"flagged": True, "result_id": str(result_id)}
