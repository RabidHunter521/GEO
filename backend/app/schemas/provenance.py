import uuid

from pydantic import BaseModel


class SourcePresence(BaseModel):
    competitor_id: uuid.UUID
    name: str


class AcquisitionSource(BaseModel):
    url: str
    domain: str
    title: str | None
    citation_count: int
    competitors_present: list[SourcePresence]


class BrandShare(BaseModel):
    competitor_id: uuid.UUID | None  # None = the client
    name: str
    sources_present: int
    share_pct: float


class ShareOfSourceResponse(BaseModel):
    last_scan_at: str | None
    total_third_party_sources: int
    client_share: BrandShare | None
    competitor_shares: list[BrandShare]
    acquisition_list: list[AcquisitionSource]
    flip_targets: list[AcquisitionSource]


class ShareOfSourceHistoryPoint(BaseModel):
    computed_at: str
    client_share_pct: float
    total_third_party_sources: int
