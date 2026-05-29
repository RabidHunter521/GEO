import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.core.constants import MAX_COMPETITORS
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorResponse,
    CompetitorIntelligenceResponse,
    CompetitorScore,
    CompetitorQueryBreakdown,
)

router = APIRouter(prefix="/clients/{client_id}/competitors", tags=["competitors"])


@router.get(
    "/intelligence",
    response_model=CompetitorIntelligenceResponse,
    dependencies=[Depends(require_api_key)],
)
def get_intelligence(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)

    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    if not latest_scan:
        return CompetitorIntelligenceResponse(
            client_ai_citability=None,
            competitors=[
                CompetitorScore(
                    id=c.id,
                    name=c.name,
                    website=c.website,
                    ai_citability=0.0,
                    queries=[],
                    is_winning=False,
                )
                for c in competitors
            ],
            last_scan_at=None,
        )

    all_results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == latest_scan.id)
        .all()
    )

    client_results = [r for r in all_results if r.competitor_id is None]
    client_citability = (
        round(sum(1 for r in client_results if r.brand_detected) / len(client_results) * 100, 1)
        if client_results
        else 0.0
    )

    competitor_scores = []
    for comp in competitors:
        comp_results = [r for r in all_results if r.competitor_id == comp.id]
        comp_citability = (
            round(sum(1 for r in comp_results if r.brand_detected) / len(comp_results) * 100, 1)
            if comp_results
            else 0.0
        )
        competitor_scores.append(
            CompetitorScore(
                id=comp.id,
                name=comp.name,
                website=comp.website,
                ai_citability=comp_citability,
                queries=[
                    CompetitorQueryBreakdown(
                        category=r.category,
                        query_text=r.query_text,
                        brand_detected=r.brand_detected,
                    )
                    for r in comp_results
                ],
                is_winning=comp_citability > client_citability,
            )
        )

    return CompetitorIntelligenceResponse(
        client_ai_citability=client_citability,
        competitors=competitor_scores,
        last_scan_at=latest_scan.completed_at.isoformat() if latest_scan.completed_at else None,
    )


@router.get(
    "",
    response_model=list[CompetitorResponse],
    dependencies=[Depends(require_api_key)],
)
def list_competitors(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return db.query(Competitor).filter(Competitor.client_id == client_id).all()


@router.post(
    "",
    response_model=CompetitorResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def add_competitor(
    client_id: uuid.UUID,
    body: CompetitorCreate,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    count = db.query(Competitor).filter(Competitor.client_id == client_id).count()
    if count >= MAX_COMPETITORS:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum {MAX_COMPETITORS} competitors per client",
        )
    comp = Competitor(client_id=client_id, **body.model_dump())
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@router.delete(
    "/{competitor_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_competitor(
    client_id: uuid.UUID,
    competitor_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    comp = (
        db.query(Competitor)
        .filter(Competitor.id == competitor_id, Competitor.client_id == client_id)
        .first()
    )
    if comp:
        db.delete(comp)
        db.commit()


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
