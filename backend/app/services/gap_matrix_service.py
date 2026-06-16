import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import WIN_LOSS_CATEGORIES
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.schemas.gap_matrix import GapCell, GapMatrixResponse, GapMatrixRow


def _visibility(results) -> float | None:
    if not results:
        return None
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def compute_gap_matrix(db: Session) -> GapMatrixResponse:
    clients = (
        db.query(Client)
        .filter(Client.archived_at.is_(None), Client.is_prospect.is_(False))
        .order_by(Client.name)
        .all()
    )
    rows: list[GapMatrixRow] = []
    for c in clients:
        latest = (
            db.query(Scan)
            .filter(Scan.client_id == c.id, Scan.status == "completed")
            .order_by(desc(Scan.completed_at), desc(Scan.id))
            .first()
        )
        cells: list[GapCell] = []
        if latest:
            competitors = {
                comp.id: comp.name
                for comp in db.query(Competitor).filter(Competitor.client_id == c.id).all()
            }
            results = db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == latest.id).all()
            for category in WIN_LOSS_CATEGORIES:
                cat = [r for r in results if r.category == category]
                client_vis = _visibility([r for r in cat if r.competitor_id is None])
                best_name, best_vis = None, None
                for comp_id, comp_name in competitors.items():
                    v = _visibility([r for r in cat if r.competitor_id == comp_id])
                    if v is not None and (best_vis is None or v > best_vis):
                        best_name, best_vis = comp_name, v
                cells.append(GapCell(
                    category=category,
                    client_visibility=client_vis,
                    top_competitor_visibility=best_vis,
                    top_competitor_name=best_name,
                    competitors_winning=bool(
                        best_vis is not None and (client_vis is None or best_vis > client_vis)
                    ),
                ))
        rows.append(GapMatrixRow(client_id=c.id, client_name=c.name, cells=cells))
    return GapMatrixResponse(categories=list(WIN_LOSS_CATEGORIES), rows=rows)
