import html
import uuid
import structlog
from datetime import timedelta
from sqlalchemy.orm import Session
from workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.report import Report
from app.services.report_service import generate_report_pdf
from app.core.time import utcnow

# A due report blocked by missing scan data is re-checked every day; alert at
# most once per this many days so the warning stays readable.
_NO_SCAN_ALERT_EVERY_DAYS = 7

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.report_tasks.generate_client_report")
def generate_client_report(client_id: str) -> dict:
    """Manual trigger — generate PDF report for one client."""
    logger.info("generate_client_report_started", client_id=client_id)
    db = SessionLocal()
    try:
        try:
            report = generate_report_pdf(uuid.UUID(client_id), db)
        except Exception as exc:
            db.rollback()
            client = db.get(Client, uuid.UUID(client_id))
            if client is not None:
                _report_problem(
                    client, db, "report_generation_failed",
                    f"Monthly report could not be generated: {str(exc)[:200]}",
                )
            raise
        return {"generated": report is not None, "client_id": client_id}
    finally:
        db.close()


@celery_app.task(name="workers.tasks.report_tasks.check_and_generate_due_reports")
def check_and_generate_due_reports() -> dict:
    """Celery Beat task — runs daily at 9am UTC. Generates reports for clients due today."""
    logger.info("check_and_generate_due_reports_started")
    db = SessionLocal()
    generated = 0
    skipped = 0
    try:
        clients = (
            db.query(Client)
            .filter(
                Client.archived_at.is_(None),
                Client.is_prospect.is_(False),
                Client.contact_email.isnot(None),
            )
            .all()
        )
        for client in clients:
            # Don't generate a second report while one is still awaiting review
            # (unsent). Otherwise an unsent report keeps advancing the clock and
            # duplicates pile up in R2.
            if _has_unsent_report(client, db):
                skipped += 1
                continue
            if not _is_report_due(client, db):
                skipped += 1
                continue
            try:
                report = generate_report_pdf(client.id, db)
                if report:
                    generated += 1
                else:
                    # Due, but no completed scan to report on. Previously a
                    # silent daily skip, so the report never arrived and nobody
                    # knew why.
                    skipped += 1
                    if not _recently_logged(client, db, "report_blocked_no_scan"):
                        _report_problem(
                            client, db, "report_blocked_no_scan",
                            "Monthly report is due but there is no completed scan in the "
                            "last 30 days. Run a scan, then generate the report.",
                        )
            except Exception as exc:
                # A failed flush leaves the session unusable; without the
                # rollback every remaining client in the loop fails too.
                db.rollback()
                logger.error(
                    "report_generation_failed",
                    client_id=str(client.id),
                    error=str(exc),
                )
                _report_problem(
                    client, db, "report_generation_failed",
                    f"Monthly report could not be generated: {str(exc)[:200]}",
                )
                skipped += 1
        logger.info("check_and_generate_due_reports_done", generated=generated, skipped=skipped)
        return {"generated": generated, "skipped": skipped}
    finally:
        db.close()


def _recently_logged(client: Client, db: Session, event_type: str) -> bool:
    since = utcnow() - timedelta(days=_NO_SCAN_ALERT_EVERY_DAYS)
    return (
        db.query(ActivityLog.id)
        .filter(
            ActivityLog.client_id == client.id,
            ActivityLog.event_type == event_type,
            ActivityLog.created_at >= since,
        )
        .first()
        is not None
    )


def _report_problem(client: Client, db: Session, event_type: str, note: str) -> None:
    """Make a report problem loud to Faris and invisible to the client: an
    activity entry on the client plus an admin alert. Best-effort, never raises
    (client-output rule 6)."""
    try:
        db.add(ActivityLog(client_id=client.id, event_type=event_type, note=note))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("report_problem_log_failed", client_id=str(client.id), error=str(exc))
    try:
        from app.services.alert_service import dispatch_admin_alert

        subject = f"[SeenBy] Monthly report problem: {client.name}"
        dispatch_admin_alert(
            subject=subject,
            html_body=f"<p><strong>{html.escape(client.name)}</strong></p><p>{html.escape(note)}</p>",
            telegram_text=f"{subject}\n{note}",
        )
    except Exception as exc:
        logger.error("report_problem_alert_failed", client_id=str(client.id), error=str(exc))


def _has_unsent_report(client: Client, db: Session) -> bool:
    """True if a generated-but-not-yet-sent report is awaiting Faris's review."""
    return (
        db.query(Report.id)
        .filter(Report.client_id == client.id, Report.sent_at.is_(None))
        .first()
        is not None
    )


def _is_report_due(client: Client, db: Session) -> bool:
    """Return True if 30 days have passed since signup (or last report)."""
    last_report: Report | None = (
        db.query(Report)
        .filter(Report.client_id == client.id)
        .order_by(Report.generated_at.desc())
        .first()
    )
    reference = last_report.generated_at if last_report else client.created_at
    return utcnow() >= reference + timedelta(days=30)

