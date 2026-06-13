"""Optional Telegram admin notifications.

A best-effort sidecar to the email alerts: if a bot token + chat id are
configured, admin alerts are also pushed to Telegram. Sending never raises —
a webhook outage must not break a scan or a manual flag.
"""
import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_TIMEOUT = 10


def send_telegram(text: str) -> None:
    """Post a message to the configured Telegram chat. No-op when unconfigured."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("telegram_send_non_200", status=resp.status_code, body=resp.text[:200])
    except Exception as exc:  # noqa: BLE001 — never propagate to the caller
        logger.warning("telegram_send_failed", error=str(exc))
