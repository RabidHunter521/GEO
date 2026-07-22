import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.core.constants import PLATFORM_LABELS
from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.competitor import Competitor
from app.schemas.scan import (
    TriggerScanRequest,
    ScanResponse,
    ScanQueryResultResponse,
    ScanWithResultsResponse,
    ScanDiffResponse,
)
from app.schemas.causality import CausalityPointResponse, CausalityResponse
from app.services.causality_service import compute_causal_trend
from app.services.scan_diff_service import compute_scan_diff
from app.services import snippet_service

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
    # Cost guardrail: stop a scan that would breach a spend cap. Alerting is
    # best-effort and must not change the 402 the client receives.
    from app.services.budget_service import check_budget
    from app.services import alert_service
    budget = check_budget(payload.client_id, db)
    if not budget.ok:
        alert_service.notify_budget_exceeded(client, budget, db)
        raise HTTPException(status_code=402, detail=budget.reason)
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
            is_control=row.ScanQueryResult.is_control,
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
    "/client/{client_id}/diff",
    response_model=ScanDiffResponse,
    dependencies=[Depends(require_api_key)],
)
def get_scan_diff(client_id: uuid.UUID, db: Session = Depends(get_db)):
    return compute_scan_diff(client_id, db)


@router.get(
    "/client/{client_id}/causality",
    response_model=CausalityResponse,
    dependencies=[Depends(require_api_key)],
)
def get_causality(client_id: uuid.UUID, db: Session = Depends(get_db)):
    trend = compute_causal_trend(client_id, db)
    return CausalityResponse(
        points=[
            CausalityPointResponse(
                scan_id=p.scan_id,
                completed_at=p.completed_at,
                optimized_frequency=p.optimized_frequency,
                control_frequency=p.control_frequency,
            )
            for p in trend.points
        ]
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


@router.get(
    "/{scan_id}/results/{result_id}/snippet.png",
    dependencies=[Depends(require_api_key)],
)
def get_result_snippet(scan_id: uuid.UUID, result_id: uuid.UUID, db: Session = Depends(get_db)):
    result = db.get(ScanQueryResult, result_id)
    if not result or result.scan_id != scan_id or result.competitor_id is not None:
        raise HTTPException(status_code=404, detail="Result not found")
    scan = db.get(Scan, scan_id)
    client = db.get(Client, scan.client_id) if scan else None
    if not client:
        raise HTTPException(status_code=404, detail="Result not found")
    competitors = [c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()]
    excerpt = snippet_service.build_excerpt(result.response_text or "", client.name, competitors)
    if not excerpt:
        raise HTTPException(status_code=404, detail="No shareable excerpt for this result")
    png = snippet_service.render_snippet_png(
        platform_label=PLATFORM_LABELS.get(result.platform, result.platform),
        brand=client.name,
        excerpt=excerpt,
    )
    return Response(content=png, media_type="image/png")
