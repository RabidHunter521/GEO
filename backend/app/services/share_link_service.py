import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import SHARE_VIEW_VISIT_GAP_MINUTES
from app.models.client import Client
from app.models.activity_log import ActivityLog


def get_share_link_url(client: Client) -> str | None:
    """Returns the client's read-only view URL, or None if no link is active."""
    if not client.share_token:
        return None
    return f"{settings.FRONTEND_BASE_URL}/view/{client.share_token}"


def share_link_is_expired(client: Client, now: datetime | None = None) -> bool:
    if client.share_token_expires_at is None:
        return False
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return now >= client.share_token_expires_at


def generate_share_token(
    client: Client, db: Session, expires_in_days: int | None = None
) -> str:
    """Create (or rotate) the client's read-only view token.

    Atomic replace: the previous token stops working the moment this commits.
    Every (re)generation sets a fresh expiry: ``expires_in_days`` from now, or
    never when None. Visit history is kept: it describes the
    client's engagement, not one particular token.
    """
    is_rotation = client.share_token is not None
    token = secrets.token_urlsafe(32)  # 256 bits — enumeration infeasible
    client.share_token = token
    # Naive UTC to match the rest of the schema (columns are timestamp-without-tz)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    client.share_token_created_at = now
    client.share_token_expires_at = (
        now + timedelta(days=expires_in_days) if expires_in_days else None
    )
    expiry_note = f" Expires in {expires_in_days} days." if expires_in_days else ""
    db.add(ActivityLog(
        client_id=client.id,
        event_type="share_link_regenerated" if is_rotation else "share_link_generated",
        note=f"Client view link {'regenerated' if is_rotation else 'generated'} for '{client.name}'.{expiry_note}",
    ))
    db.commit()
    db.refresh(client)
    return token


def revoke_share_token(client: Client, db: Session) -> None:
    """Disable the client's read-only view link."""
    if client.share_token is None:
        return
    client.share_token = None
    client.share_token_created_at = None
    client.share_token_expires_at = None
    db.add(ActivityLog(
        client_id=client.id,
        event_type="share_link_revoked",
        note=f"Client view link revoked for '{client.name}'.",
    ))
    db.commit()


def record_share_view(client: Client, db: Session, now: datetime | None = None) -> bool:
    """Record that the client opened their view link. Returns True if this
    counted as a new visit.

    Every call refreshes ``share_last_viewed_at``; only an open more than
    SHARE_VIEW_VISIT_GAP_MINUTES after the previous one counts as a new visit
    and is written to the activity log, so browsing between tabs is one visit.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    last = client.share_last_viewed_at
    is_new_visit = last is None or now - last > timedelta(minutes=SHARE_VIEW_VISIT_GAP_MINUTES)
    client.share_last_viewed_at = now
    if is_new_visit:
        client.share_view_count = (client.share_view_count or 0) + 1
        db.add(ActivityLog(
            client_id=client.id,
            event_type="share_link_opened",
            note=f"'{client.name}' opened their client view link (visit {client.share_view_count}).",
        ))
    db.commit()
    return is_new_visit
