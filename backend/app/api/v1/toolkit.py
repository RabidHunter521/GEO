import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.activity_log import ActivityLog
from app.models.toolkit_files import ToolkitFiles
from app.models.geo_score import GeoScore
from app.services.toolkit_service import generate_toolkit_files, generate_llms_full_txt
from app.services.verification_crawler import verify_all
from app.services.scoring_service import compute_geo_score
from app.schemas.toolkit import ToolkitFilesResponse, VerificationResult

router = APIRouter(prefix="/clients/{client_id}/toolkit", tags=["toolkit"])


@router.post(
    "/generate",
    response_model=ToolkitFilesResponse,
    dependencies=[Depends(require_api_key)],
)
def generate(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    files_content = generate_toolkit_files(client)

    existing = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if existing:
        existing.llms_txt = files_content["llms_txt"]
        existing.schema_json = files_content["schema_json"]
        existing.robots_txt = files_content["robots_txt"]
        existing.generated_at = datetime.now(UTC)
        existing.llms_verified = False
        existing.schema_verified = False
        existing.robots_verified = False
        existing.verified_at = None
        db.add(ActivityLog(
            client_id=client_id,
            event_type="toolkit_generated",
            note="AI Readiness Toolkit files regenerated (llms.txt, schema.json, robots.txt).",
        ))
        db.commit()
        db.refresh(existing)
        return existing

    tf = ToolkitFiles(client_id=client_id, **files_content)
    db.add(tf)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_generated",
        note="AI Readiness Toolkit files generated (llms.txt, schema.json, robots.txt).",
    ))
    db.commit()
    db.refresh(tf)
    return tf


@router.post(
    "/generate-llms-full",
    response_model=ToolkitFilesResponse,
    dependencies=[Depends(require_api_key)],
)
def generate_llms_full(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    tf = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if not tf:
        raise HTTPException(status_code=404, detail="Generate the toolkit files first")
    tf.llms_full_txt = generate_llms_full_txt(client)
    tf.llms_full_verified = False
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_generated",
        note="llms-full.txt generated.",
    ))
    db.commit()
    db.refresh(tf)
    return tf


@router.get(
    "/files",
    response_model=ToolkitFilesResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_files(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()


@router.post(
    "/verify",
    response_model=VerificationResult,
    dependencies=[Depends(require_api_key)],
)
def verify(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    tf = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client_id).first()
    if not tf:
        raise HTTPException(status_code=404, detail="No toolkit files generated yet")

    results = verify_all(client.website)

    tf.llms_verified = results["llms_verified"]
    tf.schema_verified = results["schema_verified"]
    tf.robots_verified = results["robots_verified"]
    # Informational only — llms-full never touches dimension scores (spec §6).
    tf.llms_full_verified = results["llms_full_verified"]
    if any(results.values()):
        tf.verified_at = datetime.now(UTC)

    # spec: llms.txt + robots.txt must both verify for technical_foundations
    client.technical_foundations_verified = results["llms_verified"] and results["robots_verified"]
    client.structured_data_verified = results["schema_verified"]

    verified_names = ", ".join(
        name
        for name, ok in [
            ("llms.txt", results["llms_verified"]),
            ("schema.json", results["schema_verified"]),
            ("robots.txt", results["robots_verified"]),
            ("llms-full.txt", results["llms_full_verified"]),
        ]
        if ok
    ) or "none"
    db.add(ActivityLog(
        client_id=client_id,
        event_type="toolkit_verified",
        note=f"Toolkit verification run. Files verified: {verified_names}.",
    ))

    # Recompute and persist overall GEO score when toolkit verification changes scores
    latest_geo = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(GeoScore.computed_at.desc())
        .first()
    )
    if latest_geo:
        new_overall = compute_geo_score(client, latest_geo.ai_citability)
        db.add(GeoScore(
            client_id=client.id,
            scan_id=latest_geo.scan_id,
            ai_citability=latest_geo.ai_citability,
            brand_authority=float(client.brand_authority_score),
            content_quality=float(client.content_quality_score),
            technical_foundations=100.0 if client.technical_foundations_verified else 0.0,
            structured_data=100.0 if client.structured_data_verified else 0.0,
            overall_score=new_overall,
        ))

    db.commit()

    return VerificationResult(
        llms_verified=results["llms_verified"],
        schema_verified=results["schema_verified"],
        robots_verified=results["robots_verified"],
        llms_full_verified=results["llms_full_verified"],
        technical_foundations_updated=client.technical_foundations_verified,
        structured_data_updated=client.structured_data_verified,
    )


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c
