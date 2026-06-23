import html
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
import structlog

from app.core.constants import PLATFORM_LABELS
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.activity_log import ActivityLog
from app.services.email_service import send_email
from app.services.claude_action import get_digest_action
from app.services.proof_card_service import select_proof_cards
from app.services.share_link_service import get_share_link_url

logger = structlog.get_logger()


@dataclass
class DigestData:
    seen_count: int
    total_count: int
    current_ai_citability: float
    current_overall_score: float
    prev_ai_citability: float | None
    trend: str  # "up" | "down" | "flat" | "first"
    is_first_seen: bool
    action_text: str
    # One verbatim, redacted AI-answer quote — the most forwardable piece of the
    # email. None when no client-owned win qualifies. Never raw response_text.
    proof_quote: str | None = None
    proof_platform: str | None = None


def send_client_digest(client_id: uuid.UUID, db: Session) -> bool:
    """Returns True if digest was sent, False if skipped."""
    client = db.get(Client, client_id)
    # Prospects are cold leads — a "your weekly visibility update" implies an
    # existing client relationship, so never send them one (covers both the
    # weekly beat and the manual admin trigger).
    if (
        not client
        or client.archived_at is not None
        or client.is_prospect
        or not client.contact_email
    ):
        return False

    # Idempotency: don't send a second digest in the same week (e.g. the Monday
    # beat plus a manual trigger). 6 days keeps the weekly cadence unblocked.
    already_sent = (
        db.query(ActivityLog.id)
        .filter(
            ActivityLog.client_id == client_id,
            ActivityLog.event_type == "digest_sent",
            ActivityLog.created_at >= datetime.utcnow() - timedelta(days=6),
        )
        .first()
    )
    if already_sent is not None:
        logger.info("digest_skipped_recent", client_id=str(client_id))
        return False

    data = _compute_digest_data(client, db)
    if data is None:
        return False

    # Lead with the human result (seen by AI in X of Y), keep the GEO Score in the
    # subject (CLAUDE.md §7 requires the score). The "what changed" beats the bare
    # number for opens — but the number stays so the rule holds.
    if data.total_count:
        subject = (
            f"{client.name}: seen by AI in {data.seen_count}/{data.total_count} "
            f"questions this week · GEO Score {data.current_overall_score:.0f}"
        )
    else:
        subject = (
            f"{client.name}: your AI visibility update · "
            f"GEO Score {data.current_overall_score:.0f}"
        )
    html = _build_email_html(client, data)
    send_email(to=client.contact_email, subject=subject, html_body=html)

    db.add(ActivityLog(
        client_id=client_id,
        event_type="digest_sent",
        note=f"Weekly digest sent to {client.contact_email}.",
    ))
    db.commit()
    logger.info("digest_sent", client_id=str(client_id), to=client.contact_email)
    return True


def _compute_digest_data(client: Client, db: Session) -> DigestData | None:
    since = datetime.utcnow() - timedelta(days=7)

    latest_scan: Scan | None = (
        db.query(Scan)
        .filter(
            Scan.client_id == client.id,
            Scan.status == "completed",
            Scan.completed_at >= since,
        )
        .order_by(desc(Scan.completed_at))
        .first()
    )
    if not latest_scan:
        return None

    current_gs: GeoScore | None = (
        db.query(GeoScore)
        .filter(GeoScore.scan_id == latest_scan.id)
        .first()
    )
    if not current_gs:
        return None

    prev_scan: Scan | None = (
        db.query(Scan)
        .filter(
            Scan.client_id == client.id,
            Scan.status == "completed",
            Scan.completed_at < latest_scan.completed_at,
        )
        .order_by(desc(Scan.completed_at))
        .first()
    )
    prev_gs: GeoScore | None = None
    if prev_scan:
        prev_gs = (
            db.query(GeoScore)
            .filter(GeoScore.scan_id == prev_scan.id)
            .first()
        )

    client_results = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == latest_scan.id,
            ScanQueryResult.competitor_id.is_(None),
        )
        .all()
    )
    seen_count = sum(1 for r in client_results if r.brand_detected)
    total_count = len(client_results)

    current_citability = current_gs.ai_citability
    prev_citability = prev_gs.ai_citability if prev_gs else None

    trend = _compute_trend(current_citability, prev_citability)
    is_first_seen = _detect_first_seen(seen_count, prev_scan, db)
    action_text = get_digest_action(client, current_citability, prev_citability)

    # Best verbatim win quote for the body — the single most forwardable line.
    # Excludes hallucination-flagged answers (known-bad) and competitor rows.
    competitor_names = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    proof_quote = None
    proof_platform = None
    cards = select_proof_cards(
        [r for r in client_results if not r.hallucination_flagged],
        client.name,
        competitor_names,
        win_cap=1,
        loss_cap=0,
    )
    if cards:
        proof_quote = cards[0].excerpt
        proof_platform = PLATFORM_LABELS.get(cards[0].platform, cards[0].platform.title())

    return DigestData(
        seen_count=seen_count,
        total_count=total_count,
        current_ai_citability=current_citability,
        current_overall_score=current_gs.overall_score,
        prev_ai_citability=prev_citability,
        trend=trend,
        is_first_seen=is_first_seen,
        action_text=action_text,
        proof_quote=proof_quote,
        proof_platform=proof_platform,
    )


def _compute_trend(current: float, prev: float | None) -> str:
    if prev is None:
        return "first"
    if current > prev + 0.5:
        return "up"
    if current < prev - 0.5:
        return "down"
    return "flat"


def _detect_first_seen(seen_count: int, prev_scan: Scan | None, db: Session) -> bool:
    if seen_count == 0:
        return False
    if prev_scan is None:
        return True
    prev_detected = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == prev_scan.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.brand_detected.is_(True),
        )
        .count()
    )
    return prev_detected == 0


def _build_email_html(client: Client, data: DigestData) -> str:
    trend_messages = {
        "up":    "Your AI visibility improved this week ↑",
        "down":  "Your AI visibility decreased this week ↓",
        "flat":  "Your AI visibility held steady this week →",
        "first": "This is your first SeenBy weekly update.",
    }
    trend_colors = {
        "up":    "#16a34a",
        "down":  "#dc2626",
        "flat":  "#6b7280",
        "first": "#6b7280",
    }
    trend_msg = trend_messages[data.trend]
    trend_color = trend_colors[data.trend]

    # Escape free-text fields (client name, Claude-written action) before they
    # land in the email HTML — an "&" or "<" must not break the markup.
    safe_name = html.escape(client.name)
    safe_action = html.escape(data.action_text)

    # Verbatim "straight from AI" quote — the most forwardable block. The excerpt
    # is already redacted (no raw response_text); escape it for HTML safety.
    proof_block = ""
    if data.proof_quote:
        safe_quote = html.escape(data.proof_quote)
        safe_platform = html.escape(data.proof_platform or "AI")
        proof_block = f"""
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                    padding:16px 20px;margin-bottom:20px;">
          <p style="margin:0 0 6px;font-size:12px;color:#15803d;font-weight:600;
                    text-transform:uppercase;letter-spacing:0.05em;">
            Straight from {safe_platform}
          </p>
          <p style="margin:0;font-size:15px;color:#14532d;line-height:1.6;font-style:italic;">
            &ldquo;{safe_quote}&rdquo;
          </p>
        </div>"""

    view_url = get_share_link_url(client)
    dashboard_button = ""
    if view_url:
        dashboard_button = f"""
          <div style="text-align:center;margin:24px 0 0;">
            <a href="{view_url}"
               style="display:inline-block;background:#0f172a;color:#ffffff;
                      font-size:14px;font-weight:600;text-decoration:none;
                      padding:12px 28px;border-radius:6px;">
              View Your Full Dashboard
            </a>
          </div>"""

    milestone_block = ""
    if data.is_first_seen:
        milestone_block = f"""
        <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 16px;
                    margin-bottom:20px;border-radius:4px;">
          <strong style="color:#15803d;">First time AI models saw your brand!</strong>
          <p style="margin:4px 0 0;color:#166534;font-size:14px;">
            AI models detected {safe_name} in search results for the first time this week.
          </p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f9fafb;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;border:1px solid #e5e7eb;">

        <tr><td style="background:#0f172a;padding:24px 32px;border-radius:8px 8px 0 0;">
          <p style="margin:0;color:#ffffff;font-size:20px;font-weight:700;">SeenBy</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">Weekly AI Visibility Update</p>
        </td></tr>

        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">
            {safe_name} &mdash; Weekly Update
          </h2>
          <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">
            Here is how AI models saw your brand this week.
          </p>

          {milestone_block}

          {proof_block}

          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                      padding:20px;margin-bottom:20px;">
            <p style="margin:0 0 4px;font-size:13px;color:#6b7280;
                      text-transform:uppercase;letter-spacing:0.05em;">
              AI Visibility Frequency
            </p>
            <p style="margin:0;font-size:28px;font-weight:700;color:#0f172a;">
              {data.seen_count}/{data.total_count}
            </p>
            <p style="margin:4px 0 0;font-size:14px;color:#6b7280;">
              Seen by AI <strong>{data.seen_count} out of {data.total_count} times</strong> this week.
            </p>
          </div>

          <p style="color:{trend_color};font-size:15px;font-weight:600;margin:0 0 24px;">
            {trend_msg}
          </p>

          <div style="border-top:1px solid #e5e7eb;padding-top:20px;">
            <p style="margin:0 0 8px;font-size:13px;color:#6b7280;
                      text-transform:uppercase;letter-spacing:0.05em;">
              Action This Week
            </p>
            <p style="margin:0;font-size:15px;color:#0f172a;line-height:1.6;">
              {safe_action}
            </p>
          </div>

{dashboard_button}

          <p style="margin:32px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            Tracked by SeenBy &middot;
            <a href="mailto:contact@seenby.my"
               style="color:#9ca3af;text-decoration:none;">contact@seenby.my</a>
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
