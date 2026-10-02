"""Lead-source attribution routes: admin setup/summary, the tracked WhatsApp
link, and the inbound "how did you hear about us?" webhook.

The two public routes are normally reached through the Next.js handlers at
`/wa/[token]` and `/hooks/heard-about-us`, which forward the visitor's IP,
user agent and referrer in `X-Visitor-*` headers. If they are called
directly, the request's own headers are used instead. Those values only feed
click de-duplication and AI matching — like any web analytics, a determined
visitor can spoof them, which is why the result is `attributed`, not
`observed`.
"""

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import require_api_key
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.models.client import Client
from app.schemas.attribution import (
    AttributionOverview,
    AttributionSettingUpdate,
    AttributionSignalOut,
    ChannelSummary,
    HeardAboutUsWebhook,
    ManualAnswerCreate,
    TrackedClickResult,
    WebhookResult,
    WebhookSecretOut,
)
from app.services import attribution_service
from app.services.attribution_service import AttributionValidationError

router = APIRouter(
    prefix="/clients/{client_id}/attribution",
    tags=["attribution"],
    dependencies=[Depends(require_api_key)],
)

# Separate namespaces so a burst of clicks can never starve lead webhooks.
# Generous: when proxied through Next.js, every visitor shares one upstream IP.
_click_rate_limit = rate_limit("attribution_click", max_requests=600, window_seconds=60)
_webhook_rate_limit = rate_limit("attribution_webhook", max_requests=120, window_seconds=60)

public_router = APIRouter(tags=["attribution-public"])


def _get_client_or_404(client_id: uuid.UUID, db: Session) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _overview(client_id: uuid.UUID, db: Session) -> AttributionOverview:
    setting = attribution_service.get_or_create_setting(client_id, db)
    summary = attribution_service.summarize(client_id, db)
    return AttributionOverview(
        whatsapp_number=setting.whatsapp_number,
        whatsapp_message=setting.whatsapp_message,
        tracking_enabled=setting.tracking_enabled,
        tracked_link_url=attribution_service.tracked_link_url(setting),
        website_snippet=attribution_service.build_website_snippet(setting),
        webhook_url=attribution_service.webhook_url(),
        webhook_secret_set=setting.webhook_secret_hash is not None,
        webhook_secret_created_at=setting.webhook_secret_created_at,
        window_days=summary["window_days"],
        whatsapp_clicks=ChannelSummary(**summary["channels"][attribution_service.CHANNEL_WHATSAPP]),
        heard_about_us=ChannelSummary(**summary["channels"][attribution_service.CHANNEL_HEARD]),
        recent=[
            AttributionSignalOut(
                id=s.id,
                channel=s.channel,
                occurred_at=s.occurred_at,
                ai_platform=s.ai_platform,
                match_reason=s.match_reason,
                source=s.source,
                raw_value=s.raw_value,
            )
            for s in summary["recent"]
        ],
    )


@router.get("", response_model=AttributionOverview)
def get_attribution(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    return _overview(client_id, db)


@router.put("", response_model=AttributionOverview)
def update_attribution(
    client_id: uuid.UUID, body: AttributionSettingUpdate, db: Session = Depends(get_db)
):
    _get_client_or_404(client_id, db)
    try:
        attribution_service.update_setting(
            client_id,
            db,
            whatsapp_number=body.whatsapp_number,
            whatsapp_message=body.whatsapp_message,
            tracking_enabled=body.tracking_enabled,
        )
    except AttributionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _overview(client_id, db)


@router.post("/webhook-secret", response_model=WebhookSecretOut, status_code=201)
def rotate_webhook_secret(client_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    secret, created_at = attribution_service.rotate_webhook_secret(client_id, db)
    return WebhookSecretOut(webhook_secret=secret, webhook_secret_created_at=created_at)


@router.post("/answers", response_model=WebhookResult, status_code=201)
def log_answer(client_id: uuid.UUID, body: ManualAnswerCreate, db: Session = Depends(get_db)):
    _get_client_or_404(client_id, db)
    try:
        signal, _ = attribution_service.record_answer(
            client_id,
            db,
            answer=body.answer,
            submission_id=None,
            source="manual",
            occurred_at=body.occurred_at,
            event_type=body.event_type,
            value_minor=body.value_minor,
            currency=body.currency,
        )
    except AttributionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WebhookResult(status="recorded", ai_attributed=signal.ai_platform is not None)


@public_router.get(
    "/track/whatsapp/{click_token}",
    response_model=TrackedClickResult,
    dependencies=[Depends(_click_rate_limit)],
)
def track_whatsapp_click(
    click_token: str,
    request: Request,
    fallback: str | None = Query(default=None, max_length=2000),
    ref: str | None = Query(default=None, max_length=255),
    utm: str | None = Query(default=None, max_length=255),
    x_visitor_ip: str | None = Header(default=None, max_length=64),
    x_visitor_ua: str | None = Header(default=None, max_length=512),
    x_visitor_referer: str | None = Header(default=None, max_length=2000),
    db: Session = Depends(get_db),
):
    redirect_url = attribution_service.record_whatsapp_click(
        click_token,
        db,
        fallback_url=fallback,
        landing_referrer=ref,
        landing_utm=utm,
        click_referrer=x_visitor_referer or request.headers.get("referer"),
        visitor_ip=x_visitor_ip or (request.client.host if request.client else None),
        user_agent=x_visitor_ua or request.headers.get("user-agent"),
    )
    if redirect_url is None:
        raise HTTPException(status_code=404, detail="Not found")
    return TrackedClickResult(redirect_url=redirect_url)


@public_router.post(
    "/webhooks/heard-about-us",
    response_model=WebhookResult,
    dependencies=[Depends(_webhook_rate_limit)],
)
def heard_about_us_webhook(
    body: HeardAboutUsWebhook,
    db: Session = Depends(get_db),
    x_seenby_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    """Per-client secret in `X-SeenBy-Secret` (or `Authorization: Bearer`).
    Idempotent on `submission_id`: a retry returns `duplicate` and changes
    nothing."""
    secret = x_seenby_secret
    if not secret and authorization and authorization.lower().startswith("bearer "):
        secret = authorization[7:].strip()
    setting = attribution_service.find_setting_by_secret(secret, db)
    if setting is None:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    if not setting.tracking_enabled:
        raise HTTPException(status_code=403, detail="Tracking is switched off for this client")
    try:
        signal, created = attribution_service.record_answer(
            setting.client_id,
            db,
            answer=body.answer,
            submission_id=body.submission_id,
            source="webhook",
            occurred_at=body.occurred_at,
            event_type=body.event_type,
            value_minor=body.value_minor,
            currency=body.currency,
        )
    except AttributionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return WebhookResult(
        status="recorded" if created else "duplicate",
        ai_attributed=signal.ai_platform is not None,
    )
