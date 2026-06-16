import uuid
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import get_db
from app.core.auth import require_api_key
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.schemas.client import ClientCreate, ClientUpdate, ClientResponse, ClientListItem, ShareTokenResponse
from app.schemas.geo_score import GeoScoreResponse
from app.schemas.benchmark import IndustryBenchmarkResponse
from app.services.benchmark_service import compute_industry_benchmark
from app.services.client_list_service import build_client_list
from app.services.gap_matrix_service import compute_gap_matrix
from app.services.share_link_service import generate_share_token, revoke_share_token
from app.services import r2_service
from app.schemas.gap_matrix import GapMatrixResponse

router = APIRouter(prefix="/clients", tags=["clients"])

# Sniffed PIL format → (extension, canonical content-type). The uploaded bytes
# are inspected; the client-supplied content-type is never trusted. SVG is not
# in the map — it can embed <script> and logos render in the public client view
# (stored-XSS risk) — and raster sniffing rejects it anyway.
_LOGO_FORMATS = {
    "PNG":  ("png", "image/png"),
    "JPEG": ("jpg", "image/jpeg"),
    "WEBP": ("webp", "image/webp"),
    "GIF":  ("gif", "image/gif"),
}
_LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def _sniff_logo(data: bytes) -> tuple[str, str] | None:
    """Return (ext, content_type) from the actual image bytes, or None if the
    bytes aren't a supported raster image."""
    try:
        with Image.open(BytesIO(data)) as img:
            return _LOGO_FORMATS.get(img.format)
    except (UnidentifiedImageError, OSError):
        return None


@router.get("", response_model=list[ClientListItem], dependencies=[Depends(require_api_key)])
def list_clients(db: Session = Depends(get_db)):
    return build_client_list(db)


@router.post(
    "",
    response_model=ClientResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
)
def create_client(body: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**body.model_dump())
    db.add(c)
    db.flush()  # assign c.id without committing, so both rows share one transaction
    db.add(ActivityLog(
        client_id=c.id,
        event_type="client_created",
        note=f"Client '{c.name}' added to SeenBy.",
    ))
    db.commit()
    db.refresh(c)
    return c


@router.get(
    "/gap-matrix",
    response_model=GapMatrixResponse,
    dependencies=[Depends(require_api_key)],
)
def get_gap_matrix(db: Session = Depends(get_db)):
    return compute_gap_matrix(db)


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
def update_client(client_id: uuid.UUID, body: ClientUpdate, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.post(
    "/{client_id}/logo",
    response_model=ClientResponse,
    dependencies=[Depends(require_api_key)],
)
async def upload_client_logo(
    client_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 2 MB).")

    sniffed = _sniff_logo(data)
    if not sniffed:
        raise HTTPException(
            status_code=400,
            detail="Unsupported or invalid image. Use PNG, JPG, WEBP, or GIF.",
        )
    ext, content_type = sniffed

    # Timestamp suffix busts CDN/browser cache when a logo is replaced.
    key = f"logos/{client_id}-{int(datetime.now(timezone.utc).timestamp())}.{ext}"
    # boto3 is blocking — offload so it doesn't stall the event loop.
    c.logo_url = await run_in_threadpool(
        r2_service.upload_image, key, data, content_type
    )
    db.commit()
    db.refresh(c)
    return c


@router.delete(
    "/{client_id}",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def archive_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    # Naive UTC to match the rest of the schema (columns are timestamp-without-tz)
    c.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


@router.post(
    "/{client_id}/share-token",
    response_model=ShareTokenResponse,
    dependencies=[Depends(require_api_key)],
)
def create_or_rotate_share_token(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    generate_share_token(c, db)
    return ShareTokenResponse(
        share_token=c.share_token,
        share_token_created_at=c.share_token_created_at,
    )


@router.delete(
    "/{client_id}/share-token",
    status_code=204,
    dependencies=[Depends(require_api_key)],
)
def delete_share_token(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    revoke_share_token(c, db)


@router.get(
    "/{client_id}/benchmark",
    response_model=IndustryBenchmarkResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_industry_benchmark(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return compute_industry_benchmark(c, db)


@router.get(
    "/{client_id}/geo-score/latest",
    response_model=GeoScoreResponse | None,
    dependencies=[Depends(require_api_key)],
)
def get_latest_geo_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at))
        .first()
    )
