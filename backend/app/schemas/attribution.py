"""Payloads for lead-source attribution (tracked WhatsApp link + "how did you
hear about us?" capture). Admin-only shapes, plus the public webhook body.

Nothing here is used by a client-facing view: AI-matched signals reach the
client only as `attributed` rows in the conversion ledger, summarised by
`business_impact_service`.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AnswerEventType = Literal["lead", "booking", "call", "purchase", "form_submit"]


class HeardAboutUsWebhook(BaseModel):
    """Body a form tool / CRM / Zapier step POSTs to the inbound webhook.

    Unknown fields are ignored rather than rejected: form tools send whatever
    the form has, and failing a lead because it carried an extra field would
    lose the answer we came for.
    """

    submission_id: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1, max_length=500)
    occurred_at: datetime | None = None
    event_type: AnswerEventType = "lead"
    value_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="MYR", min_length=3, max_length=3)

    model_config = {"extra": "ignore"}


class WebhookResult(BaseModel):
    status: Literal["recorded", "duplicate"]
    ai_attributed: bool


class ManualAnswerCreate(BaseModel):
    """An answer staff collected by phone / at the counter."""

    answer: str = Field(min_length=1, max_length=500)
    occurred_at: datetime | None = None
    event_type: AnswerEventType = "lead"
    value_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="MYR", min_length=3, max_length=3)

    model_config = {"extra": "forbid"}


class AttributionSettingUpdate(BaseModel):
    whatsapp_number: str | None = Field(default=None, max_length=32)
    whatsapp_message: str | None = Field(default=None, max_length=500)
    tracking_enabled: bool = True

    model_config = {"extra": "forbid"}


class ChannelSummary(BaseModel):
    total: int
    ai_attributed: int
    by_platform: dict[str, int]


class AttributionSignalOut(BaseModel):
    id: uuid.UUID
    channel: str
    occurred_at: datetime
    ai_platform: str | None
    match_reason: str | None
    source: str
    raw_value: str | None


class AttributionOverview(BaseModel):
    whatsapp_number: str | None
    whatsapp_message: str | None
    tracking_enabled: bool
    tracked_link_url: str
    website_snippet: str
    webhook_url: str
    webhook_secret_set: bool
    webhook_secret_created_at: datetime | None
    window_days: int
    whatsapp_clicks: ChannelSummary
    heard_about_us: ChannelSummary
    recent: list[AttributionSignalOut]


class WebhookSecretOut(BaseModel):
    """The plaintext secret. Returned once, at generation; never retrievable again."""

    webhook_secret: str
    webhook_secret_created_at: datetime


class TrackedClickResult(BaseModel):
    redirect_url: str
