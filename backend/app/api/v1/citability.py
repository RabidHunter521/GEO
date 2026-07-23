import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.models.client import Client
from app.models.page_audit import PageAudit
from app.schemas.citability import PageAuditListItem, PageAuditRequest, PageAuditResponse
from app.services.citability_service import OffDomainUrlError, PageFetchError, audit_page

router = APIRouter(prefix="/clients/{client_id}/page-audits", tags=["citability"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.post("", response_model=PageAuditResponse, dependencies=[Depends(require_api_key)])
def run_audit(client_id: uuid.UUID, body: PageAuditRequest, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    try:
        return audit_page(client, body.url, db)
    except OffDomainUrlError:
        raise HTTPException(
            status_code=422,
            detail="That page isn't on this client's website — audits only run on the client's own domain.",
        )
    except PageFetchError:
        raise HTTPException(
            status_code=502,
            detail="Couldn't load that page — check the address and try again.",
        )


def get_page_audit_list(client_id: uuid.UUID, db: Session) -> list[dict]:
    """Latest audit per distinct URL, with the previous score for a delta arrow."""
    rows = (
        db.query(PageAudit)
        .filter(PageAudit.client_id == client_id)
        .order_by(PageAudit.created_at.desc())
        .all()
    )
    latest: dict[str, PageAudit] = {}
    previous: dict[str, int] = {}
    for r in rows:
        if r.url not in latest:
            latest[r.url] = r
        elif r.url not in previous:
            previous[r.url] = r.score
    return [
        {
            "id": a.id, "url": a.url, "score": a.score,
            "previous_score": previous.get(url), "created_at": a.created_at,
        }
        for url, a in latest.items()
    ]


@router.get("", response_model=list[PageAuditListItem], dependencies=[Depends(require_api_key)])
def list_audits(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return get_page_audit_list(client_id, db)


@router.get("/{audit_id}", response_model=PageAuditResponse, dependencies=[Depends(require_api_key)])
def get_audit(client_id: uuid.UUID, audit_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    audit = db.get(PageAudit, audit_id)
    if not audit or audit.client_id != client_id:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit
