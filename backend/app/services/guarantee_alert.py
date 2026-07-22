"""Post-scan guarantee pace check. Best-effort by contract: callers wrap in the
scan post-commit try/except; internally a send failure is also swallowed so
last_state still persists."""
import structlog
from sqlalchemy.orm import Session

from app.models.client import Client
from app.services.guarantee_service import get_guarantee_progress

logger = structlog.get_logger()

_ALERT_STATES = ("at_risk", "deadline_passed")


def _send_admin_alert(client: Client, state: str, progress) -> None:
    # Reuse alert_service's admin dispatch (email to ALERTS_EMAIL + Telegram).
    from app.services.alert_service import dispatch_admin_alert

    g = progress.guarantee
    label = state.replace("_", " ")
    current = f"{progress.current_value:.1f}" if progress.current_value is not None else "no scan yet"
    body = (
        f"<p><strong>Client:</strong> {client.name}</p>"
        f"<p><strong>Commitment:</strong> {g.metric} {g.baseline_value} &rarr; "
        f"{g.target_value} by {g.deadline_date}</p>"
        f"<p><strong>Current:</strong> {current}</p>"
        f"<p><strong>State:</strong> {label} ({progress.days_remaining} days remaining)</p>"
    )
    dispatch_admin_alert(
        subject=f"[SeenBy] Guarantee {label}: {client.name}",
        html_body=body,
        telegram_text=(
            f"Guarantee {label}: {client.name} — {g.metric} "
            f"{g.baseline_value}→{g.target_value} by {g.deadline_date}, "
            f"current {current}, {progress.days_remaining}d left"
        ),
    )


def check_guarantee_transition(client: Client, db: Session) -> None:
    progress = get_guarantee_progress(client.id, db)
    if progress is None:
        return
    g = progress.guarantee
    state = progress.state
    if state != g.last_state and state in _ALERT_STATES:
        try:
            _send_admin_alert(client, state, progress)
        except Exception as exc:
            logger.error("guarantee_alert_send_failed", client_id=str(client.id), error=str(exc))
    g.last_state = state
    db.commit()
