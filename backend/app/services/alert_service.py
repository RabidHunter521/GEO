import uuid
from sqlalchemy.orm import Session
import structlog

from app.core.constants import ALERTS_EMAIL
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.email_service import send_email

logger = structlog.get_logger()


def check_score_drop_alert(
    client: Client,
    current_geo_score: GeoScore,
    prev_geo_score: GeoScore | None,
    db: Session,
) -> None:
    """Fires once when overall_score crosses below score_drop_threshold."""
    if prev_geo_score is None:
        return

    was_above = prev_geo_score.overall_score >= client.score_drop_threshold
    now_below = current_geo_score.overall_score < client.score_drop_threshold

    if not (was_above and now_below):
        return

    send_email(
        to=ALERTS_EMAIL,
        subject=f"Score drop alert: {client.name} — GEO Score dropped to {current_geo_score.overall_score:.0f}",
        html_body=_build_score_drop_email(
            client,
            current_geo_score.overall_score,
            prev_geo_score.overall_score,
        ),
    )
    db.add(ActivityLog(
        client_id=client.id,
        event_type="alert_sent",
        note=(
            f"Score drop alert sent. Overall GEO Score dropped from "
            f"{prev_geo_score.overall_score:.0f} to {current_geo_score.overall_score:.0f}, "
            f"crossing below threshold of {client.score_drop_threshold}."
        ),
    ))
    db.commit()
    logger.info("score_drop_alert_sent", client_id=str(client.id))


def check_competitor_overtake_alert(client: Client, scan_id: uuid.UUID, db: Session) -> None:
    """Fires for each competitor whose AI Citability now exceeds the client's."""
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    if not competitors:
        return

    all_results = (
        db.query(ScanQueryResult)
        .filter(ScanQueryResult.scan_id == scan_id)
        .all()
    )

    client_results = [r for r in all_results if r.competitor_id is None]
    client_citability = _compute_citability(client_results)

    sent = False
    for competitor in competitors:
        comp_results = [r for r in all_results if r.competitor_id == competitor.id]
        comp_citability = _compute_citability(comp_results)
        if comp_citability > client_citability:
            delta = round(comp_citability - client_citability, 1)
            send_email(
                to=ALERTS_EMAIL,
                subject=f"Competitor overtake: {competitor.name} is ahead of {client.name}",
                html_body=_build_overtake_email(
                    client, competitor.name, comp_citability, client_citability, delta
                ),
            )
            db.add(ActivityLog(
                client_id=client.id,
                event_type="alert_sent",
                note=(
                    f"Competitor overtake alert: {competitor.name} AI visibility "
                    f"({comp_citability:.0f}%) now exceeds {client.name} ({client_citability:.0f}%). "
                    f"Delta: +{delta:.0f}%."
                ),
            ))
            sent = True

    if sent:
        db.commit()
        logger.info("competitor_overtake_alert_sent", client_id=str(client.id))


def flag_hallucination(result_id: uuid.UUID, db: Session, expected_scan_id: uuid.UUID | None = None) -> None:
    """Manual hallucination flag — called from the admin scan results panel."""
    result = db.get(ScanQueryResult, result_id)
    if not result:
        raise ValueError(f"Scan query result not found: {result_id}")

    if expected_scan_id is not None and result.scan_id != expected_scan_id:
        raise ValueError(f"Result {result_id} does not belong to scan {expected_scan_id}")

    scan = db.get(Scan, result.scan_id)
    if not scan:
        raise ValueError(f"Scan not found: {result.scan_id}")
    client = db.get(Client, scan.client_id)

    result.hallucination_flagged = True
    db.add(ActivityLog(
        client_id=client.id,
        event_type="hallucination_flagged",
        note=f"Hallucination flagged on query: {result.query_text[:100]}",
    ))
    db.commit()
    logger.info("hallucination_flagged", client_id=str(client.id), result_id=str(result_id))
    try:
        send_email(
            to=ALERTS_EMAIL,
            subject=f"Hallucination flagged: {client.name}",
            html_body=_build_hallucination_email(client, result),
        )
    except Exception:
        logger.warning("hallucination_flag_email_failed", client_id=str(client.id), result_id=str(result_id))


def _compute_citability(results: list[ScanQueryResult]) -> float:
    if not results:
        return 0.0
    return round(sum(1 for r in results if r.brand_detected) / len(results) * 100, 1)


def _build_score_drop_email(client: Client, current: float, prev: float) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#dc2626;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Score Drop Alert</p>
          <p style="margin:4px 0 0;color:#fecaca;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#374151;">The overall GEO Score has crossed below the alert threshold.</p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Previous score</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{prev:.0f}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Current score</td>
              <td style="padding:8px 0;font-weight:600;color:#dc2626;text-align:right;">{current:.0f}</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Alert threshold</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{client.score_drop_threshold}</td>
            </tr>
          </table>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:{ALERTS_EMAIL}" style="color:#9ca3af;">{ALERTS_EMAIL}</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_overtake_email(
    client: Client,
    competitor_name: str,
    comp_citability: float,
    client_citability: float,
    delta: float,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#f59e0b;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Competitor Overtake Alert</p>
          <p style="margin:4px 0 0;color:#fef3c7;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#374151;">
            <strong>{competitor_name}</strong> is now ahead in AI visibility.
            Your competitors are winning here.
          </p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">{client.name} AI visibility</td>
              <td style="padding:8px 0;font-weight:600;text-align:right;">{client_citability:.0f}%</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">{competitor_name} AI visibility</td>
              <td style="padding:8px 0;font-weight:600;color:#f59e0b;text-align:right;">{comp_citability:.0f}%</td>
            </tr>
            <tr>
              <td style="padding:8px 0;color:#6b7280;font-size:14px;">Gap</td>
              <td style="padding:8px 0;font-weight:600;color:#dc2626;text-align:right;">+{delta:.0f}% ahead</td>
            </tr>
          </table>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:{ALERTS_EMAIL}" style="color:#9ca3af;">{ALERTS_EMAIL}</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_hallucination_email(client: Client, result: ScanQueryResult) -> str:
    response_preview = (result.response_text or "")[:500]
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;">
        <tr><td style="background:#7c3aed;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#fff;font-size:18px;font-weight:700;">Hallucination Flagged</p>
          <p style="margin:4px 0 0;color:#ede9fe;font-size:13px;">SeenBy Admin Notification</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;color:#0f172a;">{client.name}</h2>
          <p style="color:#6b7280;font-size:14px;font-weight:600;margin:0 0 8px;">Query</p>
          <p style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
                    padding:12px;font-size:14px;color:#374151;margin:0 0 16px;">
            {result.query_text}
          </p>
          <p style="color:#6b7280;font-size:14px;font-weight:600;margin:0 0 8px;">AI Response (excerpt)</p>
          <p style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;
                    padding:12px;font-size:14px;color:#374151;margin:0 0 0;
                    white-space:pre-wrap;word-break:break-word;">
            {response_preview}
          </p>
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:{ALERTS_EMAIL}" style="color:#9ca3af;">{ALERTS_EMAIL}</a>
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
