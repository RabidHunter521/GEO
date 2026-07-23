import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.constants import AUTHORITY_ASSET_STATUSES
from app.core.database import get_db
from app.models.authority_asset import AuthorityAsset
from app.models.client import Client
from app.schemas.authority import (
    AddAssetsRequest,
    AuthorityAssetOut,
    AuthorityViewResponse,
    CatalogItem,
    PatchAssetRequest,
    ReviewSnapshotRequest,
    VerifyResponse,
)
from app.services import authority_service

router = APIRouter(prefix="/clients/{client_id}/authority", tags=["authority"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    c = db.get(Client, client_id)
    if not c or c.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return c


def _get_asset_or_404(client_id: uuid.UUID, asset_id: uuid.UUID, db: Session) -> AuthorityAsset:
    asset = db.get(AuthorityAsset, asset_id)
    if not asset or asset.client_id != client_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def _out(asset: AuthorityAsset, seen: int = 0) -> AuthorityAssetOut:
    data = AuthorityAssetOut.model_validate(asset)
    data.seen_in_ai_sources = seen
    return data


@router.get("", response_model=AuthorityViewResponse, dependencies=[Depends(require_api_key)])
def get_authority(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    return authority_service.build_authority_view(client, db)


@router.get("/catalog", response_model=list[CatalogItem], dependencies=[Depends(require_api_key)])
def get_catalog(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    return authority_service.get_catalog(client, db)


@router.post("", response_model=list[AuthorityAssetOut], dependencies=[Depends(require_api_key)])
def add_assets(client_id: uuid.UUID, body: AddAssetsRequest, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    rows = authority_service.add_assets(client, [i.model_dump() for i in body.items], db)
    return [_out(r) for r in rows]


@router.patch("/{asset_id}", response_model=AuthorityAssetOut, dependencies=[Depends(require_api_key)])
def patch_asset(
    client_id: uuid.UUID, asset_id: uuid.UUID, body: PatchAssetRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    patch = body.model_dump(exclude_unset=True)
    if "status" in patch and patch["status"] not in AUTHORITY_ASSET_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown status.")
    asset = authority_service.update_asset(asset, patch, db)
    return _out(asset)


@router.post("/{asset_id}/verify", response_model=VerifyResponse, dependencies=[Depends(require_api_key)])
def verify(client_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db)):
    client = _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    asset, note = authority_service.verify_asset(asset, client, db)
    return VerifyResponse(asset=_out(asset), note=note)


@router.post("/{asset_id}/review-snapshot", response_model=AuthorityAssetOut, dependencies=[Depends(require_api_key)])
def review_snapshot(
    client_id: uuid.UUID, asset_id: uuid.UUID, body: ReviewSnapshotRequest,
    db: Session = Depends(get_db),
):
    _get_client_or_404(client_id, db)
    asset = _get_asset_or_404(client_id, asset_id, db)
    asset = authority_service.add_review_snapshot(asset, body.rating, body.count, db)
    return _out(asset)
