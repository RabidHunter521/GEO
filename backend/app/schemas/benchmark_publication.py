"""Publication contracts for the SEA AI Visibility Index (Phase 6 Task 7).

The public shape is the narrowest surface in the whole product: it is served
anonymously, so it carries the reviewed payload and the provenance needed to
read it honestly (edition, period, methodology version) and nothing else. No
cohort keys, no member counts, no actor names, no internal status history.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

PublicationStatus = Literal["draft", "approved", "published", "withdrawn"]


class PublicationCreate(BaseModel):
    slug: str = Field(min_length=3, max_length=128, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=3, max_length=255)
    edition: str = Field(min_length=1, max_length=64)
    period_start: date
    period_end: date
    # Who is generating this draft. Required because approval must name a
    # different actor, and there is no per-user authentication to infer it from.
    generated_by: str = Field(min_length=1, max_length=128)
    methodology_version: str = Field(default="v1", max_length=16)


class PublicationApprove(BaseModel):
    approved_by: str = Field(min_length=1, max_length=128)


class PublicationWithdraw(BaseModel):
    reason: str = Field(min_length=1)


class PublicationResponse(BaseModel):
    """Admin shape — the full audit record."""

    id: str
    slug: str
    title: str
    edition: str
    methodology_version: str
    period_start: date
    period_end: date
    status: PublicationStatus
    payload: dict
    payload_hash: str
    generated_by: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    withdrawn_at: datetime | None = None
    withdrawn_reason: str | None = None

    @classmethod
    def from_model(cls, publication) -> "PublicationResponse":
        return cls(
            id=str(publication.id),
            slug=publication.slug,
            title=publication.title,
            edition=publication.edition,
            methodology_version=publication.methodology_version,
            period_start=publication.period_start,
            period_end=publication.period_end,
            status=publication.status,
            payload=publication.payload,
            payload_hash=publication.payload_hash,
            generated_by=publication.generated_by,
            approved_by=publication.approved_by,
            approved_at=publication.approved_at,
            published_at=publication.published_at,
            withdrawn_at=publication.withdrawn_at,
            withdrawn_reason=publication.withdrawn_reason,
        )


class PublicationPublic(BaseModel):
    """Anonymous shape. A separate model, not a subclass — the admin record
    carries actor names and a draft payload, and inheritance is how those
    would eventually leak onto a public URL."""

    slug: str
    title: str
    edition: str
    methodology_version: str
    period_start: date
    period_end: date
    published_at: datetime | None = None
    payload_hash: str
    payload: dict

    @classmethod
    def from_model(cls, publication) -> "PublicationPublic":
        return cls(
            slug=publication.slug,
            title=publication.title,
            edition=publication.edition,
            methodology_version=publication.methodology_version,
            period_start=publication.period_start,
            period_end=publication.period_end,
            published_at=publication.published_at,
            payload_hash=publication.payload_hash,
            payload=publication.payload,
        )
