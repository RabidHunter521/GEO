import uuid
from datetime import datetime

from pydantic import BaseModel, field_serializer


class CatalogItem(BaseModel):
    key: str
    name: str
    type: str
    provenance_domain: str | None
    url_hint: str | None
    suggested_industries: list[str]
    added: bool


class ReviewSnapshot(BaseModel):
    date: str
    rating: float
    count: int


class AuthorityAssetOut(BaseModel):
    id: uuid.UUID
    asset_key: str | None
    name: str
    asset_type: str
    url: str | None
    status: str
    notes: str | None
    provenance_domain: str | None
    review_snapshots: list[ReviewSnapshot]
    found_nap: dict | None
    nap_mismatch: bool
    last_checked_at: datetime | None
    seen_in_ai_sources: int = 0

    model_config = {"from_attributes": True}

    @field_serializer("last_checked_at")
    def _ser_last_checked_at(self, value: datetime | None) -> str | None:
        # utcnow() stores naive UTC — stamp the Z so JS parses it as UTC, not local.
        return None if value is None else value.isoformat() + "Z"


class SuggestedDomain(BaseModel):
    domain: str
    count: int
    catalog_key: str | None


class AuthoritySummary(BaseModel):
    total: int
    live: int
    verified: int
    covered_top_domains: int
    total_top_domains: int


class AuthorityViewResponse(BaseModel):
    assets: list[AuthorityAssetOut]
    suggested_next: list[SuggestedDomain]
    summary: AuthoritySummary


class AddAssetItem(BaseModel):
    asset_key: str | None = None
    name: str | None = None
    asset_type: str | None = None
    url: str | None = None
    provenance_domain: str | None = None


class AddAssetsRequest(BaseModel):
    items: list[AddAssetItem]


class PatchAssetRequest(BaseModel):
    status: str | None = None
    url: str | None = None
    notes: str | None = None
    hidden: bool | None = None


class ReviewSnapshotRequest(BaseModel):
    rating: float
    count: int


class VerifyResponse(BaseModel):
    asset: AuthorityAssetOut
    note: str
