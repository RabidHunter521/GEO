from sqlalchemy import desc, func
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
    if not clients:
        return GapMatrixResponse(categories=list(WIN_LOSS_CATEGORIES), rows=[])

    client_ids = [c.id for c in clients]

    # Latest completed scan per client via ROW_NUMBER — one query instead of one
    # per client (id breaks completed_at ties deterministically, matching the
    # previous order_by(completed_at desc, id desc).first()).
    scan_rn = (
        func.row_number()
        .over(
            partition_by=Scan.client_id,
            order_by=(desc(Scan.completed_at), desc(Scan.id)),
        )
        .label("rn")
    )
    ranked_scans = (
        db.query(
            Scan.id.label("id"),
            Scan.client_id.label("client_id"),
            scan_rn,
        )
        .filter(Scan.client_id.in_(client_ids), Scan.status == "completed")
        .subquery()
    )
    latest_scan_id_by_client = {
        r.client_id: r.id
        for r in db.query(ranked_scans).filter(ranked_scans.c.rn == 1).all()
    }
    latest_scan_ids = list(latest_scan_id_by_client.values())

    # All competitors for these clients, grouped in memory (one query).
    competitors_by_client: dict = {cid: {} for cid in client_ids}
    for comp in db.query(Competitor).filter(Competitor.client_id.in_(client_ids)).all():
        competitors_by_client[comp.client_id][comp.id] = comp.name

    # All win/loss results for the selected scans, grouped by scan (one query).
    # Exclude hallucination-flagged rows (consistent with win_loss_service — their
    # brand_detected is unreliable).
    results_by_scan: dict = {sid: [] for sid in latest_scan_ids}
    if latest_scan_ids:
        scan_results = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id.in_(latest_scan_ids),
                ScanQueryResult.category.in_(WIN_LOSS_CATEGORIES),
                ScanQueryResult.hallucination_flagged.is_(False),
                ScanQueryResult.is_control.is_(False),
            )
            .all()
        )
        for r in scan_results:
            results_by_scan[r.scan_id].append(r)

    rows: list[GapMatrixRow] = []
    for c in clients:
        cells: list[GapCell] = []
        latest_scan_id = latest_scan_id_by_client.get(c.id)
        if latest_scan_id is not None:
            competitors = competitors_by_client.get(c.id, {})
            results = results_by_scan.get(latest_scan_id, [])
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
