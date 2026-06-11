import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client import Client
from app.models.activity_log import ActivityLog


def get_share_link_url(client: Client) -> str | None:
    """Returns the client's read-only view URL, or None if no link is active."""
    if not client.share_token:
        return None
    return f"{settings.FRONTEND_BASE_URL}/view/{client.share_token}"


def generate_share_token(client: Client, db: Session) -> str:
    """Create (or rotate) the client's read-only view token.

    Atomic replace: the previous token stops working the moment this commits.
    """
    is_rotation = client.share_token is not None
    token = secrets.token_urlsafe(32)  # 256 bits — enumeration infeasible
    client.share_token = token
    client.share_token_created_at = datetime.now(timezone.utc)
    db.add(ActivityLog(
        client_id=client.id,
        event_type="share_link_regenerated" if is_rotation else "share_link_generated",
        note=f"Client view link {'regenerated' if is_rotation else 'generated'} for '{client.name}'.",
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
    db.add(ActivityLog(
        client_id=client.id,
        event_type="share_link_revoked",
        note=f"Client view link revoked for '{client.name}'.",
    ))
    db.commit()
