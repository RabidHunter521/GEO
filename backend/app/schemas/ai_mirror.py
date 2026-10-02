"""AI Mirror response shapes (see app/services/ai_mirror_service.py).

The client-view models are a whitelist: verbatim excerpts and derived counts
only, never the raw answer. The admin models add the full stored answer and the
inaccuracy flag for the team.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MirrorStatus = Literal["ready", "no_scan", "no_competitors"]
SideStatus = Literal["seen", "not_seen", "no_answer"]
CompetitorBasis = Literal["buyer_answers", "visibility"]


class ClientViewMirrorSide(BaseModel):
    name: str
    question: str | None
    status: SideStatus
    excerpts: list[str] = []


class ClientViewMirrorPlatform(BaseModel):
    platform_label: str
    same_question: bool
    you: ClientViewMirrorSide
    competitor: ClientViewMirrorSide
    buyer_answers_total: int
    buyer_answers_you: int
    buyer_answers_competitor: int


class ClientViewMirror(BaseModel):
    status: MirrorStatus
    checked_at: datetime | None = None
    competitor_name: str | None = None
    competitor_basis: CompetitorBasis | None = None
    platforms: list[ClientViewMirrorPlatform] = []


class AiMirrorSide(ClientViewMirrorSide):
    response_text: str | None = None
    flagged_inaccurate: bool = False


class AiMirrorPlatform(ClientViewMirrorPlatform):
    platform: str
    you: AiMirrorSide
    competitor: AiMirrorSide


class AiMirrorResponse(ClientViewMirror):
    platforms: list[AiMirrorPlatform] = []
