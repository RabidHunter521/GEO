"""The invite / password-reset email for admin accounts.

Admin-facing, but still from contact@seenby.my and carrying the company
identity line like every other email.
"""
import html

import structlog

from app.core.config import settings
from app.core.constants import COMPANY_IDENTITY_LINE, USER_INVITE_TTL_HOURS
from app.models.user import User
from app.services.email_service import send_email

logger = structlog.get_logger()


def link_url(raw_token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/auth/invite/{raw_token}"


def build_invite_email(user: User, raw_token: str, *, is_reset: bool, invited_by: str | None) -> tuple[str, str]:
    url = html.escape(link_url(raw_token))
    name = html.escape(user.name)
    if is_reset:
        subject = "Reset your SeenBy sign-in"
        intro = "A new sign-in link was issued for your SeenBy admin account."
    else:
        subject = "You're invited to the SeenBy admin panel"
        who = html.escape(invited_by) if invited_by else "The SeenBy owner"
        intro = f"{who} has invited you to the SeenBy admin panel."
    body = f"""<!doctype html>
<html><body style="margin:0;background:#f8fafc;font-family:Inter,Arial,sans-serif;color:#0f172a;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;"><tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;">
      <tr><td style="padding:32px;">
        <p style="margin:0 0 16px;font-size:16px;">Hi {name},</p>
        <p style="margin:0 0 16px;font-size:16px;line-height:1.6;">{intro}</p>
        <p style="margin:0 0 24px;font-size:16px;line-height:1.6;">
          Use the button below to choose a password and connect an authenticator
          app (Google Authenticator, 1Password, Authy…). Both are required to sign in.
        </p>
        <p style="margin:0 0 24px;">
          <a href="{url}" style="display:inline-block;background:#5b3cf5;color:#ffffff;text-decoration:none;
             font-weight:600;padding:12px 20px;border-radius:8px;">Set up my account</a>
        </p>
        <p style="margin:0 0 8px;font-size:13px;color:#64748b;">
          This link works once and expires in {USER_INVITE_TTL_HOURS} hours. If you weren't
          expecting it, you can ignore this email.
        </p>
        <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;border-top:1px solid #f3f4f6;padding-top:16px;">
          SeenBy &middot; contact@seenby.my<br>{html.escape(COMPANY_IDENTITY_LINE)}
        </p>
      </td></tr>
    </table>
  </td></tr></table>
</body></html>"""
    return subject, body


def send_invite_email(user: User, raw_token: str, *, is_reset: bool = False, invited_by: str | None = None) -> bool:
    """Best-effort send. Returns False on failure so the caller can show the
    link to the owner to share by hand instead."""
    subject, body = build_invite_email(user, raw_token, is_reset=is_reset, invited_by=invited_by)
    try:
        send_email(user.email, subject, body)
        return True
    except Exception:  # noqa: BLE001 — the owner can still copy the link
        logger.warning("user_invite_email_failed", user_id=str(user.id))
        return False
