"""Client win notifications — "ChatGPT now recommends you for ...".

Runs after every completed scan (best-effort post-commit step in
scan_service.run_scan). It finds buyer questions where the client newly became
recommended, or newly Seen by AI, on a platform, records each confirmed win in
`client_wins`, and — only when the client has win notifications switched on —
tells them through the available client channels (email today; WhatsApp is an
adapter in notification_channels).

What counts as a win (deliberately conservative, see docs/methodology.md: "a
single observed change is evidence, not proof"):

  * Only neutral buyer questions (WIN_CATEGORIES: recommendation + local).
  * Only the client's own, non-control, non-hallucination-flagged rows.
  * Per scan, a question's answer is the MAJORITY of its observed samples
    (a sample with no stored answer is unobserved and never counts as "not
    seen"). A question with no observed sample in any compared scan is skipped.
  * The new answer must hold in each of the last WIN_CONFIRMING_SCANS completed
    scans, AND be absent in the scan just before them. So nothing can fire
    before a client has WIN_CONFIRMING_SCANS + 1 completed scans.
  * Every compared scan must come from the same known score formula version
    (scoring_service.scores_comparable): v1.3.0 changed how "seen" is decided,
    so a flip across versions may be a measurement change, not a real one.
  * "recommended" = Seen by AI with a list position (recommendation_position).
    It outranks "seen" for the same question, and a client already seen but
    newly placed in the list counts as a recommended win.
  * The same platform + question + kind never notifies twice inside
    WIN_RENOTIFY_DAYS.
"""
import html
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import (
    COMPANY_IDENTITY_LINE,
    PLATFORM_LABELS,
    WIN_CATEGORIES,
    WIN_CONFIRMING_SCANS,
    WIN_MESSAGE_MAX_LISTED,
    WIN_RENOTIFY_DAYS,
)
from app.core.time import utcnow
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.client_win import ClientWin
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.notification_channels import CLIENT_CHANNELS, ClientMessage, NotificationChannel
from app.services.scoring_service import scores_comparable
from app.services.share_link_service import get_share_link_url

logger = structlog.get_logger()

_Key = tuple[str, str, str]  # (platform, category, query_text)
_NUMBER_WORDS = {2: "two", 3: "three", 4: "four"}


@dataclass(frozen=True)
class _Answer:
    seen: bool
    recommended: bool
    best_position: int | None


@dataclass(frozen=True)
class WinCandidate:
    platform: str
    category: str
    query_text: str
    kind: str  # "recommended" | "seen"
    recommendation_position: int | None


def _answers_for_scan(scan_id: uuid.UUID, db: Session) -> dict[_Key, _Answer]:
    rows = (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQueryResult.hallucination_flagged.is_(False),
            ScanQueryResult.category.in_(WIN_CATEGORIES),
            # No stored answer = unobserved (provider failed, or purged after
            # 90 days). Never read that as "not seen".
            ScanQueryResult.response_text.isnot(None),
        )
        .all()
    )
    grouped: dict[_Key, list[ScanQueryResult]] = defaultdict(list)
    for r in rows:
        grouped[(r.platform, r.category, r.query_text)].append(r)

    answers: dict[_Key, _Answer] = {}
    for key, samples in grouped.items():
        n = len(samples)
        seen = sum(1 for s in samples if s.brand_detected)
        ranked = [
            s.recommendation_position
            for s in samples
            if s.brand_detected and s.recommendation_position is not None
        ]
        answers[key] = _Answer(
            seen=seen * 2 > n,
            recommended=len(ranked) * 2 > n,
            best_position=min(ranked) if ranked else None,
        )
    return answers


def _recent_scans(client_id: uuid.UUID, db: Session) -> list[Scan]:
    return (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at), desc(Scan.id))
        .limit(WIN_CONFIRMING_SCANS + 1)
        .all()
    )


def _same_formula(scans: list[Scan], db: Session) -> bool:
    versions = []
    for s in scans:
        row = db.query(GeoScore.score_version).filter(GeoScore.scan_id == s.id).first()
        versions.append(row[0] if row else None)
    return all(scores_comparable(versions[0], v) for v in versions[1:])


def detect_wins(client_id: uuid.UUID, db: Session) -> tuple[list[WinCandidate], list[Scan]]:
    """Wins confirmed by the latest completed scan, before dedupe.

    Returns (wins, scans) where scans are newest-first: the confirming scans
    followed by the baseline scan. Read-only.
    """
    scans = _recent_scans(client_id, db)
    if len(scans) < WIN_CONFIRMING_SCANS + 1 or not _same_formula(scans, db):
        return [], scans

    confirming = [_answers_for_scan(s.id, db) for s in scans[:WIN_CONFIRMING_SCANS]]
    baseline = _answers_for_scan(scans[WIN_CONFIRMING_SCANS].id, db)

    wins: list[WinCandidate] = []
    for key, latest in confirming[0].items():
        before = baseline.get(key)
        held = [c.get(key) for c in confirming]
        if before is None or any(a is None for a in held):
            continue
        platform, category, query_text = key
        if all(a.recommended for a in held) and not before.recommended:
            wins.append(WinCandidate(platform, category, query_text, "recommended", latest.best_position))
        elif all(a.seen for a in held) and not before.seen:
            wins.append(WinCandidate(platform, category, query_text, "seen", None))
    # Recommended first, then best position, then a stable text order.
    wins.sort(key=lambda w: (w.kind != "recommended", w.recommendation_position or 99, w.platform, w.query_text))
    return wins, scans


def _already_recorded(client_id: uuid.UUID, win: WinCandidate, db: Session) -> bool:
    cutoff = utcnow() - timedelta(days=WIN_RENOTIFY_DAYS)
    return (
        db.query(ClientWin.id)
        .filter(
            ClientWin.client_id == client_id,
            ClientWin.platform == win.platform,
            ClientWin.query_text == win.query_text,
            ClientWin.kind == win.kind,
            ClientWin.detected_at >= cutoff,
        )
        .first()
        is not None
    )


def _win_line_text(win: ClientWin) -> str:
    label = PLATFORM_LABELS.get(win.platform, win.platform)
    if win.kind == "recommended":
        line = f'{label} now recommends you when asked "{win.query_text}"'
        if win.recommendation_position is not None:
            line += f" (AI Search Ranking #{win.recommendation_position})"
        return line
    return f'You are now Seen by AI on {label} when asked "{win.query_text}"'


def _subject(client: Client, wins: list[ClientWin]) -> str:
    if len(wins) == 1:
        w = wins[0]
        label = PLATFORM_LABELS.get(w.platform, w.platform)
        q = w.query_text if len(w.query_text) <= 80 else w.query_text[:77].rstrip() + "..."
        if w.kind == "recommended":
            return f'Good news: {label} now recommends {client.name} for "{q}"'
        return f'Good news: {client.name} is now Seen by AI on {label} for "{q}"'
    return f"Good news: {client.name} has {len(wins)} new wins in AI answers"


def build_win_message(client: Client, wins: list[ClientWin], scans: list[Scan]) -> ClientMessage:
    """Render the client message. Every claim comes from stored scan rows."""
    listed = wins[:WIN_MESSAGE_MAX_LISTED]
    more = len(wins) - len(listed)
    confirm_dates = sorted(
        s.completed_at.strftime("%d %b %Y") for s in scans[:WIN_CONFIRMING_SCANS] if s.completed_at
    )
    confirm_line = (
        f"Confirmed in your last {_NUMBER_WORDS.get(WIN_CONFIRMING_SCANS, WIN_CONFIRMING_SCANS)} scans ({' and '.join(confirm_dates)}). "
        "AI answers vary from one run to the next, so we only report a change once it repeats."
    )
    more_line = f"And {more} more." if more > 0 else ""
    view_url = get_share_link_url(client)

    text_lines = [f"Good news for {client.name}!", ""]
    text_lines += [f"- {_win_line_text(w)}" for w in listed]
    if more_line:
        text_lines.append(more_line)
    text_lines += ["", confirm_line]
    if view_url:
        text_lines += ["", f"See the details: {view_url}"]
    text_lines += ["", COMPANY_IDENTITY_LINE]

    items_html = "".join(
        f"""
            <li style="margin:0 0 10px;color:#14532d;font-size:15px;line-height:1.5;">
              {html.escape(_win_line_text(w))}
            </li>"""
        for w in listed
    )
    more_html = (
        f'<p style="margin:0 0 16px;color:#166534;font-size:14px;">{html.escape(more_line)}</p>'
        if more_line else ""
    )
    button_html = (
        f"""
          <div style="text-align:center;margin:24px 0 0;">
            <a href="{html.escape(view_url)}"
               style="display:inline-block;background:#0f172a;color:#ffffff;
                      font-size:14px;font-weight:600;text-decoration:none;
                      padding:12px 28px;border-radius:6px;">
              See the details
            </a>
          </div>"""
        if view_url else ""
    )
    html_body = f"""<!DOCTYPE html>
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
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">A new win in AI answers</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 16px;font-size:18px;color:#0f172a;">
            Good news for {html.escape(client.name)}
          </h2>
          <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                      padding:16px 20px 6px;margin-bottom:16px;">
            <ul style="margin:0;padding:0 0 0 18px;">{items_html}
            </ul>
          </div>
          {more_html}
          <p style="margin:0;font-size:13px;color:#6b7280;line-height:1.5;">
            {html.escape(confirm_line)}
          </p>{button_html}
          <p style="margin:24px 0 0;font-size:12px;color:#9ca3af;
                    border-top:1px solid #f3f4f6;padding-top:16px;">
            SeenBy &middot;
            <a href="mailto:contact@seenby.my" style="color:#9ca3af;">contact@seenby.my</a>
            <br>{html.escape(COMPANY_IDENTITY_LINE)}
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return ClientMessage(subject=_subject(client, wins), html_body=html_body, text_body="\n".join(text_lines))


def _deliver(
    client: Client, message: ClientMessage, channels: tuple[NotificationChannel, ...]
) -> tuple[list[str], list[str]]:
    """Send on every available channel, isolating each failure.
    Returns (delivered, failed) channel names."""
    delivered: list[str] = []
    failed: list[str] = []
    for channel in channels:
        if not channel.is_available(client):
            continue
        try:
            channel.send(client, message)
            delivered.append(channel.name)
        except Exception as exc:
            failed.append(channel.name)
            logger.error("win_notification_channel_failed", client_id=str(client.id), channel=channel.name, error=str(exc))
    return delivered, failed


def process_client_wins(
    client_id: uuid.UUID,
    scan_id: uuid.UUID,
    db: Session,
    channels: tuple[NotificationChannel, ...] = CLIENT_CHANNELS,
) -> list[ClientWin]:
    """Record wins confirmed by `scan_id` and notify the client if enabled.

    Called post-commit from run_scan. Only acts when `scan_id` is the client's
    latest completed scan. Returns the newly recorded wins.
    """
    client = db.get(Client, client_id)
    if client is None or client.archived_at is not None:
        return []

    candidates, scans = detect_wins(client_id, db)
    if not scans or scans[0].id != scan_id or not candidates:
        return []

    new = [c for c in candidates if not _already_recorded(client_id, c, db)]
    if not new:
        return []

    now = utcnow()
    rows = [
        ClientWin(
            client_id=client_id,
            scan_id=scan_id,
            platform=c.platform,
            category=c.category,
            query_text=c.query_text,
            kind=c.kind,
            recommendation_position=c.recommendation_position,
            status="pending",
            detected_at=now,
        )
        for c in new
    ]
    db.add_all(rows)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="client_win_detected",
        note=f"{len(rows)} confirmed win(s): " + "; ".join(_win_line_text(r) for r in rows[:3])
        + (f"; and {len(rows) - 3} more." if len(rows) > 3 else "."),
    ))
    # Commit the ledger BEFORE sending: if anything after the send fails, the
    # rows still exist and dedupe stops a second send on retry.
    db.commit()
    logger.info("client_wins_detected", client_id=str(client_id), count=len(rows))

    can_notify = client.win_notifications_enabled and not client.is_prospect
    if not can_notify or not any(ch.is_available(client) for ch in channels):
        for r in rows:
            r.status = "not_sent"
        db.commit()
        return rows

    message = build_win_message(client, rows, scans)
    delivered, failed = _deliver(client, message, channels)
    if delivered:
        for r in rows:
            r.status = "sent"
            r.channels = ",".join(delivered)
            r.notified_at = utcnow()
        db.add(ActivityLog(
            client_id=client_id,
            event_type="win_notification_sent",
            note=f"Win notification sent by {', '.join(delivered)}: {message.subject}",
        ))
        db.commit()
        logger.info("win_notification_sent", client_id=str(client_id), channels=delivered)
    else:
        for r in rows:
            r.status = "failed"
        db.add(ActivityLog(
            client_id=client_id,
            event_type="win_notification_failed",
            note=f"Win notification could not be delivered ({', '.join(failed)}).",
        ))
        db.commit()
        # Loud to Faris, invisible to the client.
        try:
            from app.services.alert_service import dispatch_admin_alert
            dispatch_admin_alert(
                subject=f"Win notification failed: {client.name}",
                html_body=(
                    f"<p>A win notification for {html.escape(client.name)} could not be "
                    f"delivered ({html.escape(', '.join(failed))}). The wins are recorded; "
                    "nothing was sent to the client.</p>"
                ),
                telegram_text=f"⚠️ <b>{html.escape(client.name)}</b>: win notification failed.",
            )
        except Exception:
            logger.warning("win_notification_failure_alert_failed", client_id=str(client_id))
    return rows
