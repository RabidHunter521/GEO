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


class DomainAnswers(BaseModel):
    domain: str
    answers: int  # answers on this platform that drew on the domain


class PlatformSourceBreakdown(BaseModel):
    """One platform's slice of the sources AI drew on (admin-only)."""
    platform: str
    total_third_party_sources: int
    client_share_pct: float
    top_domains: list[DomainAnswers]


class ShareOfSourceResponse(BaseModel):
    last_scan_at: str | None
    total_third_party_sources: int
    client_share: BrandShare | None
    competitor_shares: list[BrandShare]
    acquisition_list: list[AcquisitionSource]
    flip_targets: list[AcquisitionSource]
    # Per-platform slices of the latest scan (admin read model only; never on
    # a snapshot or the client view). Platforms with no checked sources omitted.
    by_platform: list[PlatformSourceBreakdown] = []


class ShareOfSourceHistoryPoint(BaseModel):
    computed_at: str
    client_share_pct: float
    total_third_party_sources: int
    # True when this point's capture version or platforms differ from the
    # previous point's: the source pool changed, so the move into this point
    # is a new baseline, not a change in standing.
    coverage_changed: bool = False
