import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.competitor import Competitor
from app.schemas.site_audit import (
    CompetitorSiteAuditResponse,
    SiteAuditLatestResponse,
    SiteAuditResponse,
)
from app.services.site_audit_service import (
    get_latest_with_delta,
    run_and_persist_site_audit,
    run_site_audit,
    summarize,
)

router = APIRouter(prefix="/clients/{client_id}/site-audit", tags=["site-audit"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.post("", response_model=SiteAuditResponse, dependencies=[Depends(require_api_key)])
def run_audit(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    if not client.website:
        raise HTTPException(status_code=400, detail="Client has no website on file")
    return run_and_persist_site_audit(client_id, client.website, db)


@router.get(
    "/latest",
    response_model=SiteAuditLatestResponse | None,
    dependencies=[Depends(require_api_key)],
)
def latest(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return get_latest_with_delta(client_id, db)


@router.post(
    "/competitor/{competitor_id}",
    response_model=CompetitorSiteAuditResponse,
    dependencies=[Depends(require_api_key)],
)
def competitor_audit(
    client_id: uuid.UUID, competitor_id: uuid.UUID, db: Session = Depends(get_db)
):
    """Live audit of a competitor site — same checks, never persisted.

    A competitor's readiness never feeds the client's score (spec §4).
    """
    _get_client_or_404(client_id, db)
    comp = db.get(Competitor, competitor_id)
    if not comp or comp.client_id != client_id:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if not comp.website:
        raise HTTPException(status_code=400, detail="Competitor has no website on file")
    checks = run_site_audit(comp.website)
    s = summarize(checks)
    return CompetitorSiteAuditResponse(
        competitor_id=comp.id,
        name=comp.name,
        website=comp.website,
        checks=checks,
        passed=s["passed"],
        warned=s["warned"],
        failed=s["failed"],
        unknown=s["unknown"],
        note="Live check — not saved. A competitor's results never affect this client's score.",
    )
