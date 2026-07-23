import uuid

from pydantic import BaseModel


class SiteAIReadiness(BaseModel):
    name: str
    website: str | None = None
    # False only when no website is on file — distinct from "checked, found nothing".
    checked: bool
    has_llms_txt: bool
    blocked_ai_bots: list[str] = []
    schema_types: list[str] = []
    competitor_id: uuid.UUID | None = None


class CompetitorAIReadinessResponse(BaseModel):
    client: SiteAIReadiness
    competitors: list[SiteAIReadiness]
