import uuid

from sqlalchemy.orm import Session

from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.competitor import (
    CompetitorIntelligenceResponse,
    CompetitorScore,
    CompetitorQueryBreakdown,
)


def compute_competitor_intelligence(client_id: uuid.UUID, db: Session) -> CompetitorIntelligenceResponse:
    """Per-competitor visibility breakdown from the latest completed scan.

    Shared by the admin competitors page and the read-only client view.
    Caller is responsible for verifying the client exists / is not archived.
    """
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
        last_scan_at=latest_scan.completed_at.isoformat() + "Z" if latest_scan.completed_at else None,
    )
