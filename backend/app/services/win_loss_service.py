# backend/app/services/win_loss_service.py
"""Win/loss query analysis — pure post-processing of stored scan responses.

For the latest completed scan, checks each of the client's own neutral-intent
query answers for competitor brand presence. Admin-only surface: relies on
response_text, which is never exposed through the client view API.

Reads only the latest scan, so the 90-day raw-response retention window
rarely matters; results older than that degrade to "no competitors seen".
"""
import uuid

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import WIN_LOSS_CATEGORIES
from app.models.competitor import Competitor
from app.models.content_brief import ContentBrief
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.brand_detection import detect_brand_mention
from app.schemas.competitor import (
    ContentBriefResponse,
    WinLossEntry,
    WinLossResponse,
)


def classify_result(client_seen: bool, competitors_seen: list[str]) -> str:
    if client_seen:
        return "shared" if competitors_seen else "won"
    return "lost" if competitors_seen else "open"


def compute_win_loss(client_id: uuid.UUID, db: Session) -> WinLossResponse:
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return WinLossResponse(scan_id=None, last_scan_at=None, summary={}, entries=[])

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.category.in_(WIN_LOSS_CATEGORIES),
            ScanQueryResult.hallucination_flagged.is_(False),
        )
        .order_by(ScanQueryResult.category, ScanQueryResult.created_at)
        .all()
    )

    briefs_by_result = {
        b.scan_query_result_id: b
        for b in db.query(ContentBrief)
        .filter(ContentBrief.scan_query_result_id.in_([r.id for r in results]))
        .all()
    } if results else {}

    entries: list[WinLossEntry] = []
    summary = {"won": 0, "lost": 0, "shared": 0, "open": 0}
    for r in results:
        competitors_seen = [
            c.name for c in competitors if detect_brand_mention(r.response_text, c.name)
        ]
        outcome = classify_result(r.brand_detected, competitors_seen)
        summary[outcome] += 1
        brief = briefs_by_result.get(r.id)
        entries.append(WinLossEntry(
            result_id=r.id,
            platform=r.platform,
            category=r.category,
            query_text=r.query_text,
            client_seen=r.brand_detected,
            competitors_seen=competitors_seen,
            outcome=outcome,
            brief=ContentBriefResponse.model_validate(brief) if brief else None,
        ))

    return WinLossResponse(
        scan_id=latest_scan.id,
        last_scan_at=latest_scan.completed_at.isoformat() + "Z" if latest_scan.completed_at else None,
        summary=summary,
        entries=entries,
    )
