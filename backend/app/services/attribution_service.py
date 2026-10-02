"""Lead-source attribution: tracked WhatsApp clicks and "how did you hear about
us?" answers, fed into the conversion ledger as `attributed` evidence.

Two inputs, one rule:

- **WhatsApp clicks.** The client's site sends WhatsApp buttons through the
  tracked link `/wa/<click_token>` (the website snippet rewrites them, keeping
  each button's own number). The snippet remembers how the visitor first
  arrived (landing referrer + utm_source); if that was an AI assistant, the
  click is AI-attributed.
- **Heard-about-us answers.** A form tool / CRM posts the answer to the
  inbound webhook (per-client secret), or staff log it by hand. An answer
  naming an AI assistant is AI-attributed (self-reported).

Every signal is stored in `attribution_signals`. Only AI-matched ones also
write a `ConversionEvent` with `evidence_level="attributed"` — never
`observed` (we did not watch the AI conversation) and never `estimated`
(nothing is modelled). The match rule is kept in the event's admin-only
`metadata_json`. Clicks carry no money value; an answer carries whatever value
the sender supplied.

The click path must never stop a customer reaching the business: a disabled
setting, a bot, a duplicate or a recording failure all still redirect.
"""

import hashlib
import hmac
import json
import re
import secrets
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    AI_REFERRER_DOMAINS,
    AI_SELF_REPORT_KEYWORDS,
    WHATSAPP_CLICK_DEDUPE_MINUTES,
    WHATSAPP_REDIRECT_HOSTS,
)
from app.core.time import utcnow
from app.models.attribution_setting import AttributionSetting
from app.models.attribution_signal import AttributionSignal
from app.models.client import Client
from app.models.conversion_event import ConversionEvent
from app.services.conversion_evidence_service import ALLOWED_CURRENCIES

logger = structlog.get_logger()

CHANNEL_WHATSAPP = "whatsapp_click"
CHANNEL_HEARD = "heard_about_us"
SUMMARY_WINDOW_DAYS = 90
_RECENT_LIMIT = 20
_GENERIC_AI_LABEL = "AI assistant"

# Link-preview fetchers and crawlers follow links without a human behind them.
# They still get redirected, but are never counted.
_BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|headless|"
    r"python-requests|curl|wget|httpclient",
    re.IGNORECASE,
)
_KEYWORD_PATTERNS = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", re.IGNORECASE), label)
    for keyword, label in AI_SELF_REPORT_KEYWORDS
]


class AttributionValidationError(ValueError):
    """Raised for an invalid WhatsApp number, currency, or similar input."""


# ── Setup ────────────────────────────────────────────────────────────────────


def get_or_create_setting(client_id: uuid.UUID, db: Session) -> AttributionSetting:
    setting = db.query(AttributionSetting).filter(AttributionSetting.client_id == client_id).first()
    if setting is None:
        setting = AttributionSetting(client_id=client_id, click_token=secrets.token_urlsafe(16))
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def normalize_whatsapp_number(raw: str | None) -> str | None:
    """Digits only, international format. "+60 12-345 6789" -> "60123456789"."""
    if raw is None or not raw.strip():
        return None
    digits = re.sub(r"[\s\-().+]", "", raw.strip())
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise AttributionValidationError(
            "WhatsApp number must be in international format, e.g. +60 12-345 6789"
        )
    if digits.startswith("0"):
        raise AttributionValidationError(
            "Include the country code instead of a leading 0, e.g. +60 12-345 6789"
        )
    return digits


def update_setting(
    client_id: uuid.UUID,
    db: Session,
    *,
    whatsapp_number: str | None,
    whatsapp_message: str | None,
    tracking_enabled: bool,
) -> AttributionSetting:
    setting = get_or_create_setting(client_id, db)
    setting.whatsapp_number = normalize_whatsapp_number(whatsapp_number)
    setting.whatsapp_message = (whatsapp_message or "").strip() or None
    setting.tracking_enabled = tracking_enabled
    db.commit()
    db.refresh(setting)
    return setting


def rotate_webhook_secret(client_id: uuid.UUID, db: Session) -> tuple[str, datetime]:
    """Issue a new webhook secret, invalidating the old one. Returns the
    plaintext — the only time it is ever available."""
    setting = get_or_create_setting(client_id, db)
    secret = "sbwh_" + secrets.token_urlsafe(32)
    setting.webhook_secret_hash = _hash_secret(secret)
    setting.webhook_secret_created_at = utcnow()
    db.commit()
    return secret, setting.webhook_secret_created_at


def find_setting_by_secret(secret: str | None, db: Session) -> AttributionSetting | None:
    if not secret or len(secret) > 200:
        return None
    setting = (
        db.query(AttributionSetting)
        .filter(AttributionSetting.webhook_secret_hash == _hash_secret(secret))
        .first()
    )
    if setting is None:
        return None
    client = db.get(Client, setting.client_id)
    if client is None or client.archived_at is not None:
        return None
    return setting


def tracked_link_url(setting: AttributionSetting) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/wa/{setting.click_token}"


def webhook_url() -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/hooks/heard-about-us"


def build_website_snippet(setting: AttributionSetting) -> str:
    """Copy-paste <script> for the client's site.

    On the first page of a visit it remembers where the visitor came from
    (referrer host + utm_source, sessionStorage only — no cookies, no personal
    data). It then points every WhatsApp link on the page at the tracked link,
    passing the original link along so the visitor lands on exactly the chat
    the button was built for.
    """
    target = json.dumps(tracked_link_url(setting))
    return (
        "<script>\n"
        "(function(){var K='seenby_src',s,d={},T=" + target + ";\n"
        "try{s=window.sessionStorage;if(!s.getItem(K)){var r='';"
        "try{r=document.referrer?new URL(document.referrer).hostname:''}catch(e){}\n"
        "if(r===location.hostname)r='';"
        "s.setItem(K,JSON.stringify({r:r,u:new URLSearchParams(location.search).get('utm_source')||''}))}\n"
        "d=JSON.parse(s.getItem(K)||'{}')}catch(e){}\n"
        "function fix(a){if(a.getAttribute('data-seenby'))return;a.setAttribute('data-seenby','1');"
        "var q=new URLSearchParams();if(d.r)q.set('ref',d.r);if(d.u)q.set('utm',d.u);"
        "q.set('fallback',a.href);a.href=T+'?'+q.toString()}\n"
        "function scan(){document.querySelectorAll('a[href*=\"wa.me/\"],a[href*=\"whatsapp.com/send\"]')"
        ".forEach(fix)}\n"
        "scan();if(window.MutationObserver)new MutationObserver(scan)"
        ".observe(document.documentElement,{childList:true,subtree:true})})();\n"
        "</script>"
    )


# ── Classification ───────────────────────────────────────────────────────────


def _host_of(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        raw = urlparse(raw).hostname or ""
    return raw.split("/")[0].split(":")[0]


def _ai_domain_label(host: str) -> str | None:
    for domain, label in AI_REFERRER_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return None


def classify_answer(text: str | None, *, allow_generic: bool = True) -> str | None:
    """AI platform named in free text, or None. "ChatGPT" -> "ChatGPT",
    "saw it on google" -> None. The generic "AI" bucket can be turned off for
    inputs like utm_source where "ai" is too loose to trust."""
    if not text:
        return None
    for pattern, label in _KEYWORD_PATTERNS:
        if label == _GENERIC_AI_LABEL and not allow_generic:
            continue
        if pattern.search(text):
            return label
    return None


def classify_visit(
    *, landing_referrer: str | None, landing_utm: str | None, click_referrer: str | None
) -> tuple[str | None, str | None]:
    """(platform label, rule) for a click, or (None, None).

    Landing referrer first (how the visitor reached the site), then the
    landing utm_source (ChatGPT tags outbound links utm_source=chatgpt.com),
    then the click request's own Referer — only useful when the tracked link
    itself was shown on an AI surface.
    """
    label = _ai_domain_label(_host_of(landing_referrer))
    if label:
        return label, "referrer"
    utm = (landing_utm or "").strip().lower()[:100]
    if utm:
        label = _ai_domain_label(_host_of(utm)) or classify_answer(utm, allow_generic=False)
        if label:
            return label, "utm"
    label = _ai_domain_label(_host_of(click_referrer))
    if label:
        return label, "referrer"
    return None, None


# ── WhatsApp clicks ──────────────────────────────────────────────────────────


def _safe_whatsapp_url(url: str | None) -> str | None:
    """Return `url` only if it is an https link to WhatsApp itself."""
    if not url or len(url) > 2000:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in WHATSAPP_REDIRECT_HOSTS:
        return None
    if parsed.username or parsed.password or parsed.port:
        return None
    return parsed.geturl()


def _configured_whatsapp_url(setting: AttributionSetting) -> str | None:
    if not setting.whatsapp_number:
        return None
    url = f"https://wa.me/{setting.whatsapp_number}"
    if setting.whatsapp_message:
        url += "?text=" + quote(setting.whatsapp_message, safe="")
    return url


def _visitor_hash(client_id: uuid.UUID, ip: str | None, user_agent: str | None) -> str | None:
    if not ip:
        return None
    # Keyed, so the stored value cannot be reversed back to an IP address by
    # brute-forcing the IPv4 space.
    message = f"{client_id}|{ip}|{user_agent or ''}".encode()
    return hmac.new(settings.ADMIN_API_KEY.encode(), message, hashlib.sha256).hexdigest()


def record_whatsapp_click(
    click_token: str,
    db: Session,
    *,
    fallback_url: str | None = None,
    landing_referrer: str | None = None,
    landing_utm: str | None = None,
    click_referrer: str | None = None,
    visitor_ip: str | None = None,
    user_agent: str | None = None,
) -> str | None:
    """Record one click and return where to send the visitor, or None if the
    token is unknown or there is nowhere safe to send them (-> 404).

    The button's own WhatsApp link wins over the configured number, so a site
    with one button per branch keeps each branch's number.
    """
    if not click_token or len(click_token) > 64:
        return None
    setting = db.query(AttributionSetting).filter(AttributionSetting.click_token == click_token).first()
    if setting is None:
        return None
    client = db.get(Client, setting.client_id)
    if client is None or client.archived_at is not None:
        # Archived: stop counting, but never strand a customer mid-click.
        return _safe_whatsapp_url(fallback_url)

    redirect_url = _safe_whatsapp_url(fallback_url) or _configured_whatsapp_url(setting)
    if redirect_url is None:
        return None
    if not setting.tracking_enabled or _BOT_UA.search(user_agent or ""):
        return redirect_url

    try:
        _store_click(
            setting,
            db,
            landing_referrer=landing_referrer,
            landing_utm=landing_utm,
            click_referrer=click_referrer,
            visitor_ip=visitor_ip,
            user_agent=user_agent,
        )
    except Exception as exc:  # never block the redirect on a recording failure
        db.rollback()
        logger.warning("whatsapp_click_record_failed", client_id=str(setting.client_id), error=str(exc))
    return redirect_url


def _store_click(
    setting: AttributionSetting,
    db: Session,
    *,
    landing_referrer: str | None,
    landing_utm: str | None,
    click_referrer: str | None,
    visitor_ip: str | None,
    user_agent: str | None,
) -> None:
    now = utcnow()
    visitor = _visitor_hash(setting.client_id, visitor_ip, user_agent)
    if visitor is not None:
        recent = (
            db.query(AttributionSignal.id)
            .filter(
                AttributionSignal.client_id == setting.client_id,
                AttributionSignal.channel == CHANNEL_WHATSAPP,
                AttributionSignal.visitor_hash == visitor,
                AttributionSignal.occurred_at >= now - timedelta(minutes=WHATSAPP_CLICK_DEDUPE_MINUTES),
            )
            .first()
        )
        if recent is not None:
            return

    platform, rule = classify_visit(
        landing_referrer=landing_referrer, landing_utm=landing_utm, click_referrer=click_referrer
    )
    raw = _host_of(landing_referrer) or (landing_utm or "").strip()[:100] or _host_of(click_referrer)
    signal = AttributionSignal(
        id=uuid.uuid4(),
        client_id=setting.client_id,
        channel=CHANNEL_WHATSAPP,
        occurred_at=now,
        ai_platform=platform,
        match_reason=rule,
        source="tracked_link",
        raw_value=raw[:500] if raw else None,
        visitor_hash=visitor,
    )
    signal.external_id = str(signal.id)
    if platform:
        event = ConversionEvent(
            client_id=setting.client_id,
            event_type="whatsapp_click",
            source="whatsapp_link",
            external_event_id=f"wa:{signal.id}",
            evidence_level="attributed",
            occurred_at=now,
            value_minor=0,
            currency="MYR",
            metadata_json={"rule": rule, "ai_platform": platform, "signal_id": str(signal.id)},
        )
        db.add(event)
        db.flush()
        signal.conversion_event_id = event.id
    db.add(signal)
    db.commit()


# ── Heard-about-us answers ───────────────────────────────────────────────────


def _to_naive_utc(value: datetime | None, now: datetime) -> datetime:
    if value is None:
        return now
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    # A clock-skewed or bogus future timestamp is pinned to "now" rather than
    # parking an event in a reporting window that has not happened yet.
    return min(value, now)


def record_answer(
    client_id: uuid.UUID,
    db: Session,
    *,
    answer: str,
    submission_id: str | None,
    source: str,
    occurred_at: datetime | None = None,
    event_type: str = "lead",
    value_minor: int = 0,
    currency: str = "MYR",
) -> tuple[AttributionSignal, bool]:
    """Store one answer. Returns (signal, created). Idempotent on
    `submission_id`: a retried webhook returns the original signal untouched.

    `source` is "webhook" or "manual"; manual entries get a generated ID.
    """
    currency = currency.upper()
    if currency not in ALLOWED_CURRENCIES:
        raise AttributionValidationError(f"Unsupported currency: {currency!r}")
    external_id = submission_id or f"manual:{uuid.uuid4()}"

    existing = _find_answer(client_id, external_id, db)
    if existing is not None:
        return existing, False

    now = utcnow()
    when = _to_naive_utc(occurred_at, now)
    answer = answer.strip()[:500]
    platform = classify_answer(answer)
    signal = AttributionSignal(
        id=uuid.uuid4(),
        client_id=client_id,
        channel=CHANNEL_HEARD,
        external_id=external_id,
        occurred_at=when,
        ai_platform=platform,
        match_reason="self_reported" if platform else None,
        source=source,
        raw_value=answer,
    )
    if platform:
        event = ConversionEvent(
            client_id=client_id,
            event_type=event_type,
            source="lead_form" if source == "webhook" else "manual",
            external_event_id=f"hau:{external_id}"[:255],
            evidence_level="attributed",
            occurred_at=when,
            value_minor=value_minor,
            currency=currency,
            metadata_json={
                "rule": "self_reported",
                "ai_platform": platform,
                "signal_id": str(signal.id),
            },
        )
        db.add(event)
        db.flush()
        signal.conversion_event_id = event.id
    db.add(signal)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent retry of the same submission won the race.
        db.rollback()
        existing = _find_answer(client_id, external_id, db)
        if existing is None:
            raise
        return existing, False
    return signal, True


def _find_answer(client_id: uuid.UUID, external_id: str, db: Session) -> AttributionSignal | None:
    return (
        db.query(AttributionSignal)
        .filter(
            AttributionSignal.client_id == client_id,
            AttributionSignal.channel == CHANNEL_HEARD,
            AttributionSignal.external_id == external_id,
        )
        .first()
    )


# ── Summary ──────────────────────────────────────────────────────────────────


def summarize(client_id: uuid.UUID, db: Session, *, days: int = SUMMARY_WINDOW_DAYS) -> dict:
    since = utcnow() - timedelta(days=days)
    signals = (
        db.query(AttributionSignal)
        .filter(AttributionSignal.client_id == client_id, AttributionSignal.occurred_at >= since)
        .order_by(AttributionSignal.occurred_at.desc(), AttributionSignal.id.asc())
        .all()
    )
    channels = {}
    for channel in (CHANNEL_WHATSAPP, CHANNEL_HEARD):
        rows = [s for s in signals if s.channel == channel]
        by_platform = Counter(s.ai_platform for s in rows if s.ai_platform)
        channels[channel] = {
            "total": len(rows),
            "ai_attributed": sum(by_platform.values()),
            "by_platform": dict(by_platform.most_common()),
        }
    return {"window_days": days, "channels": channels, "recent": signals[:_RECENT_LIMIT]}


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
