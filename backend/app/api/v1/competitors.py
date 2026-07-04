import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.core.constants import MAX_COMPETITORS, WIN_LOSS_CATEGORIES
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.competitor import (
    CompetitorCreate,
    CompetitorResponse,
    CompetitorIntelligenceResponse,
    CompetitorTrendsResponse,
    ContentBriefResponse,
    WinLossResponse,
)
from app.schemas.provenance import ShareOfSourceResponse
from app.services.brand_detection import detect_brand_mention
from app.services.competitor_intelligence_service import (
    compute_competitor_intelligence,
    compute_competitor_trends,
)
from app.services.content_brief_service import generate_brief_for_result
from app.services.provenance_service import compute_share_of_source
from app.services.win_loss_service import compute_win_loss

router = APIRouter(prefix="/clients/{client_id}/competitors", tags=["competitors"])


@router.get(
    "/intelligence",
    response_model=CompetitorIntelligenceResponse,
    dependencies=[Depends(require_api_key)],
)
def get_intelligence(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return compute_competitor_intelligence(client_id, db)


@router.get(
    "/win-loss",
    response_model=WinLossResponse,
    dependencies=[Depends(require_api_key)],
)
def get_win_loss(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return compute_win_loss(client_id, db)


@router.get(
    "/trends",
    response_model=CompetitorTrendsResponse,
    dependencies=[Depends(require_api_key)],
)
def get_trends(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return compute_competitor_trends(client_id, db)


@router.get(
    "/provenance",
    response_model=ShareOfSourceResponse,
    dependencies=[Depends(require_api_key)],
)
def get_provenance(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return compute_share_of_source(client_id, db)


@router.post(
    "/win-loss/{result_id}/brief",
    response_model=ContentBriefResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_brief(
    client_id: uuid.UUID,
    result_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    client = _get_client_or_404(client_id, db)

    result = (
        db.query(ScanQueryResult)
        .join(Scan, Scan.id == ScanQueryResult.scan_id)
        .filter(
            ScanQueryResult.id == result_id,
            ScanQueryResult.competitor_id.is_(None),
            Scan.client_id == client_id,
        )
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Scan result not found")
    if result.category not in WIN_LOSS_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail="Content briefs are only available for recommendation and local queries",
        )
    if result.brand_detected:
        raise HTTPException(
            status_code=422,
            detail="Client is already seen by AI for this query",
        )

    # competitors_seen recomputed server-side — request body is never trusted
    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()
    competitors_seen = [
        c.name for c in competitors if detect_brand_mention(result.response_text, c.name)
    ]

    brief = generate_brief_for_result(client, result, competitors_seen, db)
    if brief is None:
        raise HTTPException(status_code=502, detail="Brief generation failed — try again")
    return brief


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
    client = _get_client_or_404(client_id, db)
    new_name = body.name.strip()
    if new_name.casefold() == (client.name or "").strip().casefold():
        raise HTTPException(
            status_code=422,
            detail="A competitor cannot have the same name as the client.",
        )
    existing = db.query(Competitor).filter(Competitor.client_id == client_id).all()
    if any(c.name.strip().casefold() == new_name.casefold() for c in existing):
        raise HTTPException(
            status_code=422,
            detail=f"'{new_name}' is already tracked as a competitor.",
        )
    if len(existing) >= MAX_COMPETITORS:
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
