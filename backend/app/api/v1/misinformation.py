import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import (
    COMPLIANCE_RULES,
    MISINFORMATION_CATEGORY_LABELS,
    PLATFORM_LABELS,
)
from app.core.database import get_db
from app.models.client import Client
from app.models.misinformation_finding import MisinformationFinding
from app.models.scan_query_result import ScanQueryResult
from app.schemas.misinformation import (
    MisinformationFindingResponse,
    MisinformationQueueResponse,
    MisinformationReviewRequest,
)
from app.services.misinformation_service import (
    get_findings,
    mark_corrected,
    resolve_finding,
    review_finding,
)

router = APIRouter(prefix="/clients/{client_id}/misinformation", tags=["misinformation"])


def _require_client(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _require_finding(
    client_id: uuid.UUID, finding_id: uuid.UUID, db: Session
) -> MisinformationFinding:
    finding = db.get(MisinformationFinding, finding_id)
    if not finding or finding.client_id != client_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


def _out(finding: MisinformationFinding, db: Session) -> MisinformationFindingResponse:
    result = db.get(ScanQueryResult, finding.scan_query_result_id)
    platform = result.platform if result else ""
    return MisinformationFindingResponse(
        id=finding.id,
        quote=finding.quote,
        category=finding.category,
        category_label=MISINFORMATION_CATEGORY_LABELS.get(finding.category, "Incorrect statement"),
        rule_key=finding.rule_key,
        rule_text=COMPLIANCE_RULES.get(finding.rule_key) if finding.rule_key else None,
        truth_fact_id=finding.truth_fact_id,
        truth_fact_version_id=finding.truth_fact_version_id,
        severity=finding.severity,
        explanation=finding.explanation,
        status=finding.status,
        platform=platform,
        platform_label=PLATFORM_LABELS.get(platform, platform.title() or "AI platform"),
        query_text=result.query_text if result else "",
        detected_at=finding.detected_at,
        reviewed_at=finding.reviewed_at,
        resolved_at=finding.resolved_at,
        admin_note=finding.admin_note,
    )


@router.get(
    "",
    response_model=MisinformationQueueResponse,
    dependencies=[Depends(require_api_key)],
)
def list_findings(client_id: uuid.UUID, db: Session = Depends(get_db)):
    """The admin review queue. Admin-only: unreviewed findings and verbatim AI
    quotes live here and must never be served to a client surface."""
    _require_client(client_id, db)
    findings = get_findings(client_id, db)
    return MisinformationQueueResponse(
        findings=[_out(f, db) for f in findings],
        counts=dict(Counter(f.status for f in findings)),
    )


@router.post(
    "/{finding_id}/review",
    response_model=MisinformationFindingResponse,
    dependencies=[Depends(require_api_key)],
)
def review(
    client_id: uuid.UUID,
    finding_id: uuid.UUID,
    body: MisinformationReviewRequest,
    db: Session = Depends(get_db),
):
    """Confirm (spawns a tracked corrective item) or dismiss a finding."""
    _require_client(client_id, db)
    _require_finding(client_id, finding_id, db)
    finding = review_finding(finding_id, body.action, db, note=body.note, severity=body.severity)
    if finding is None:
        raise HTTPException(
            status_code=409,
            detail="This finding has already been reviewed and is being worked on",
        )
    return _out(finding, db)


@router.post(
    "/{finding_id}/corrected",
    response_model=MisinformationFindingResponse,
    dependencies=[Depends(require_api_key)],
)
def set_corrected(client_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db)):
    """Mark the corrective work done — proof still comes from a later scan."""
    _require_client(client_id, db)
    _require_finding(client_id, finding_id, db)
    finding = mark_corrected(finding_id, db)
    if finding is None:
        raise HTTPException(status_code=409, detail="Only a confirmed finding can be corrected")
    return _out(finding, db)


@router.post(
    "/{finding_id}/resolve",
    response_model=MisinformationFindingResponse,
    dependencies=[Depends(require_api_key)],
)
def resolve(client_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db)):
    """Confirm the fix held. Allowed only once a later scan stopped showing the
    statement (status candidate_fixed) — the admin gates the good news too."""
    _require_client(client_id, db)
    _require_finding(client_id, finding_id, db)
    finding = resolve_finding(finding_id, db)
    if finding is None:
        raise HTTPException(
            status_code=409,
            detail="Only a finding a later scan no longer shows can be resolved",
        )
    return _out(finding, db)
