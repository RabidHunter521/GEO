import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import structlog
import resend as resend_module

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings

try:
    import weasyprint  # noqa: F401 — used when generating PDF bytes
except ImportError:
    weasyprint = None  # type: ignore[assignment]

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.competitor import Competitor
from app.models.toolkit_files import ToolkitFiles
from app.models.activity_log import ActivityLog
from app.models.report import Report
from app.services.scoring_service import get_score_band
from app.services.r2_service import upload_pdf, download_pdf
from app.services.claude_action import get_digest_action

logger = structlog.get_logger()

_CSS = """
@page {
  size: A4;
  margin: 2cm;
}
* { box-sizing: border-box; }
body {
  font-family: Arial, Helvetica, sans-serif;
  color: #1e293b;
  font-size: 11pt;
  line-height: 1.6;
  margin: 0;
}
.page-break { page-break-after: always; }
.cover { text-align: center; padding-top: 80px; }
.logo { font-size: 28pt; font-weight: 700; color: #0f172a; }
.cover-client { font-size: 22pt; font-weight: 700; color: #0f172a; margin-top: 60px; }
.cover-period { font-size: 13pt; color: #64748b; margin-top: 6px; }
.score-box {
  display: inline-block; background: #0f172a; color: #ffffff;
  border-radius: 12px; padding: 24px 56px; margin-top: 56px;
}
.score-box-value { font-size: 52pt; font-weight: 700; line-height: 1; }
.score-box-label { font-size: 11pt; color: #94a3b8; margin-top: 4px; }
.cover-footer { margin-top: 60px; font-size: 10pt; color: #94a3b8; }
h2 {
  font-size: 13pt; font-weight: 700; color: #0f172a;
  border-bottom: 2px solid #e2e8f0;
  padding-bottom: 6px; margin-top: 28px; margin-bottom: 14px;
}
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
th {
  background: #f8fafc; padding: 8px 12px; text-align: left;
  font-weight: 600; color: #64748b; font-size: 9pt;
  text-transform: uppercase; letter-spacing: 0.05em;
  border-bottom: 1px solid #e2e8f0;
}
td { padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }
.score-green { color: #16a34a; font-weight: 600; }
.score-yellow { color: #ca8a04; font-weight: 600; }
.score-red { color: #dc2626; font-weight: 600; }
.badge-green { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.badge-yellow { background: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.badge-red { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 9pt; }
.stat-box {
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;
}
.stat-label { font-size: 9pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { font-size: 24pt; font-weight: 700; color: #0f172a; line-height: 1.2; }
.stat-sub { font-size: 10pt; color: #64748b; margin-top: 4px; }
.rec-box { background: #f0f9ff; border-left: 4px solid #0284c7; padding: 14px 16px; border-radius: 4px; }
.manual-note { font-size: 8pt; color: #94a3b8; font-style: italic; margin-top: 2px; }
"""


@dataclass
class CompetitorSummary:
    name: str
    ai_citability: float
    is_winning: bool


@dataclass
class ReportData:
    period_start: datetime
    period_end: datetime
    period_label: str
    overall_score: float
    score_band: str
    score_color: str
    ai_citability: float
    brand_authority: float
    content_quality: float
    technical_foundations: float
    structured_data: float
    prev_overall_score: float | None
    trend: str
    seen_count: int
    total_count: int
    llms_verified: bool
    schema_verified: bool
    robots_verified: bool
    competitors: list[CompetitorSummary] = field(default_factory=list)
    recommendation: str = ""


def _compute_trend(current: float, prev: float | None) -> str:
    if prev is None:
        return "first"
    if current > prev + 0.5:
        return "up"
    if current < prev - 0.5:
        return "down"
    return "flat"


def _score_css(color: str) -> str:
    return {"green": "score-green", "yellow": "score-yellow", "red": "score-red"}.get(color, "score-red")


def _verified_badge(verified: bool) -> str:
    return '<span class="badge-green">Verified</span>' if verified else '<span class="badge-red">Not Verified</span>'


def _gather_report_data(client: Client, db: Session) -> ReportData | None:
    since = datetime.utcnow() - timedelta(days=30)

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
        db.query(GeoScore).filter(GeoScore.scan_id == latest_scan.id).first()
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
    prev_gs: GeoScore | None = (
        db.query(GeoScore).filter(GeoScore.scan_id == prev_scan.id).first()
        if prev_scan else None
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

    competitors_orm = db.query(Competitor).filter(Competitor.client_id == client.id).all()
    competitor_summaries: list[CompetitorSummary] = []
    for comp in competitors_orm:
        comp_results = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == latest_scan.id,
                ScanQueryResult.competitor_id == comp.id,
            )
            .all()
        )
        if comp_results:
            detected = sum(1 for r in comp_results if r.brand_detected)
            citability = round((detected / len(comp_results)) * 100, 2)
            competitor_summaries.append(
                CompetitorSummary(
                    name=comp.name,
                    ai_citability=citability,
                    is_winning=citability > current_gs.ai_citability,
                )
            )

    toolkit = db.query(ToolkitFiles).filter(ToolkitFiles.client_id == client.id).first()
    score_band, score_color = get_score_band(current_gs.overall_score)
    trend = _compute_trend(
        current_gs.overall_score, prev_gs.overall_score if prev_gs else None
    )
    recommendation = get_digest_action(
        client, current_gs.ai_citability, prev_gs.ai_citability if prev_gs else None
    )

    now = datetime.utcnow()
    return ReportData(
        period_start=now - timedelta(days=30),
        period_end=now,
        period_label=now.strftime("%B %Y"),
        overall_score=current_gs.overall_score,
        score_band=score_band,
        score_color=score_color,
        ai_citability=current_gs.ai_citability,
        brand_authority=current_gs.brand_authority,
        content_quality=current_gs.content_quality,
        technical_foundations=current_gs.technical_foundations,
        structured_data=current_gs.structured_data,
        prev_overall_score=prev_gs.overall_score if prev_gs else None,
        trend=trend,
        seen_count=seen_count,
        total_count=total_count,
        llms_verified=toolkit.llms_verified if toolkit else False,
        schema_verified=toolkit.schema_verified if toolkit else False,
        robots_verified=toolkit.robots_verified if toolkit else False,
        competitors=competitor_summaries,
        recommendation=recommendation,
    )


def _build_report_html(client: Client, data: ReportData) -> str:
    _, ai_color = get_score_band(data.ai_citability)
    _, ba_color = get_score_band(data.brand_authority)
    _, cq_color = get_score_band(data.content_quality)
    _, tf_color = get_score_band(data.technical_foundations)
    _, sd_color = get_score_band(data.structured_data)

    trend_messages = {
        "up":    f"&#8593; Score improved from {data.prev_overall_score:.0f} to {data.overall_score:.0f}",
        "down":  f"&#8595; Score decreased from {data.prev_overall_score:.0f} to {data.overall_score:.0f}",
        "flat":  f"&#8594; Score held steady at {data.overall_score:.0f}",
        "first": "First AI Visibility Report",
    }
    trend_colors = {"up": "#16a34a", "down": "#dc2626", "flat": "#6b7280", "first": "#6b7280"}
    trend_msg = trend_messages[data.trend]
    trend_color = trend_colors[data.trend]

    if data.competitors:
        comp_rows = "".join(
            f"""<tr>
              <td>{c.name}</td>
              <td class="{_score_css(get_score_band(c.ai_citability)[1])}">{c.ai_citability:.0f}%</td>
              <td>{"<span class='badge-red'>Winning</span>" if c.is_winning else "<span class='badge-green'>You are ahead</span>"}</td>
            </tr>"""
            for c in data.competitors
        )
    else:
        comp_rows = '<tr><td colspan="3" style="color:#9ca3af;">No competitors tracked yet.</td></tr>'

    generated_date = datetime.utcnow().strftime("%d %B %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>{_CSS}</style>
</head>
<body>

  <div class="cover page-break">
    <div class="logo">SeenBy</div>
    <div style="font-size:11pt;color:#64748b;margin-top:4px;">AI Visibility Intelligence</div>
    <div class="cover-client">{client.name}</div>
    <div class="cover-period">AI Visibility Report &middot; {data.period_label}</div>
    <div style="margin-top:56px;">
      <div class="score-box">
        <div class="score-box-value">{data.overall_score:.0f}</div>
        <div class="score-box-label">GEO Score &middot; {data.score_band.title()}</div>
      </div>
    </div>
    <div class="cover-footer">
      Report generated {generated_date}<br>
      Tracked by SeenBy &middot; contact@seenby.my
    </div>
  </div>

  <h2>AI Visibility Score</h2>
  <p style="font-size:12pt;font-weight:600;color:{trend_color};margin-bottom:16px;">{trend_msg}</p>
  <div class="stat-box">
    <div class="stat-label">Overall GEO Score</div>
    <div class="stat-value">{data.overall_score:.0f} <span style="font-size:14pt;color:#64748b;">/ 100</span></div>
    <div class="stat-sub">{data.score_band.title()} band</div>
  </div>

  <h2>Score Breakdown</h2>
  <table>
    <thead>
      <tr><th>Dimension</th><th>Score</th><th>Weight</th><th>Contribution</th><th>Source</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>AI Citability</td>
        <td class="{_score_css(ai_color)}">{data.ai_citability:.0f}</td>
        <td>40%</td><td>{data.ai_citability * 0.40:.1f}</td>
        <td>Automatic &mdash; Scan engine</td>
      </tr>
      <tr>
        <td>Brand Authority</td>
        <td class="{_score_css(ba_color)}">{data.brand_authority:.0f}</td>
        <td>20%</td><td>{data.brand_authority * 0.20:.1f}</td>
        <td>Assessed by SeenBy team<div class="manual-note">Manual assessment</div></td>
      </tr>
      <tr>
        <td>Content Quality</td>
        <td class="{_score_css(cq_color)}">{data.content_quality:.0f}</td>
        <td>20%</td><td>{data.content_quality * 0.20:.1f}</td>
        <td>Assessed by SeenBy team<div class="manual-note">Manual assessment</div></td>
      </tr>
      <tr>
        <td>Technical Foundations</td>
        <td class="{_score_css(tf_color)}">{data.technical_foundations:.0f}</td>
        <td>10%</td><td>{data.technical_foundations * 0.10:.1f}</td>
        <td>Automatic &mdash; Toolkit verified</td>
      </tr>
      <tr>
        <td>Structured Data</td>
        <td class="{_score_css(sd_color)}">{data.structured_data:.0f}</td>
        <td>10%</td><td>{data.structured_data * 0.10:.1f}</td>
        <td>Automatic &mdash; Toolkit verified</td>
      </tr>
    </tbody>
  </table>

  <h2>AI Visibility Frequency</h2>
  <div class="stat-box">
    <div class="stat-label">Seen by AI</div>
    <div class="stat-value">{data.seen_count}/{data.total_count}</div>
    <div class="stat-sub">
      {client.name} was seen by AI in {data.seen_count} out of {data.total_count} queries this period.
    </div>
  </div>

  <h2>Competitor Comparison</h2>
  <table>
    <thead><tr><th>Name</th><th>AI Citability</th><th>Status</th></tr></thead>
    <tbody>
      <tr>
        <td><strong>{client.name} (You)</strong></td>
        <td class="{_score_css(ai_color)}">{data.ai_citability:.0f}%</td>
        <td>&mdash;</td>
      </tr>
      {comp_rows}
    </tbody>
  </table>

  <h2>AI Readiness Toolkit</h2>
  <table>
    <thead><tr><th>File</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>llms.txt</td><td>{_verified_badge(data.llms_verified)}</td></tr>
      <tr><td>schema.json (JSON-LD)</td><td>{_verified_badge(data.schema_verified)}</td></tr>
      <tr><td>robots.txt (AI Bots)</td><td>{_verified_badge(data.robots_verified)}</td></tr>
    </tbody>
  </table>

  <h2>Recommended Action</h2>
  <div class="rec-box">
    <p style="margin:0;font-size:11pt;color:#0c4a6e;">{data.recommendation}</p>
  </div>

  <p style="margin-top:40px;font-size:9pt;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:12px;">
    This report was generated automatically by SeenBy. Manual dimension scores (Brand Authority,
    Content Quality) are assessed by the SeenBy team. Contact: contact@seenby.my
  </p>

</body>
</html>"""


def generate_report_pdf(client_id: uuid.UUID, db: Session) -> Report | None:
    """Generate PDF, upload to R2, save record. Returns None if client archived or no scan data."""
    client = db.get(Client, client_id)
    if not client or client.archived_at is not None:
        return None

    data = _gather_report_data(client, db)
    if data is None:
        logger.warning("no_scan_data_for_report", client_id=str(client_id))
        return None

    html = _build_report_html(client, data)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    key = f"reports/{client_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    r2_url = upload_pdf(key, pdf_bytes)

    report = Report(
        client_id=client_id,
        r2_key=key,
        r2_url=r2_url,
        period_start=data.period_start,
        period_end=data.period_end,
        overall_score=data.overall_score,
    )
    db.add(report)
    db.add(ActivityLog(
        client_id=client_id,
        event_type="report_generated",
        note=f"Monthly report generated for {data.period_label}.",
    ))
    db.commit()
    db.refresh(report)
    logger.info("report_generated", client_id=str(client_id), report_id=str(report.id))
    return report


def send_report_email(report_id: uuid.UUID, db: Session) -> bool:
    """Download PDF from R2, email to client with attachment, mark sent. Returns False if already sent."""
    report = db.get(Report, report_id)
    if not report or report.sent_at is not None:
        return False

    client = db.get(Client, report.client_id)
    if not client or not client.contact_email:
        return False

    pdf_bytes = download_pdf(report.r2_key)
    period_label = report.period_start.strftime("%B %Y")
    filename = f"SeenBy-Report-{period_label.replace(' ', '-')}.pdf"

    resend_module.api_key = settings.RESEND_API_KEY
    resend_module.Emails.send({
        "from": "contact@seenby.my",
        "to": [client.contact_email],
        "subject": f"Your Monthly AI Visibility Report — {period_label} | {client.name}",
        "html": _build_report_email_html(client, report, period_label),
        "attachments": [{"filename": filename, "content": list(pdf_bytes)}],
    })

    report.sent_at = datetime.utcnow()
    db.add(ActivityLog(
        client_id=report.client_id,
        event_type="report_sent",
        note=f"Monthly report sent to {client.contact_email} for {period_label}.",
    ))
    db.commit()
    logger.info("report_sent", report_id=str(report_id), to=client.contact_email)
    return True


def _build_report_email_html(client: Client, report: Report, period_label: str) -> str:
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
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">Monthly AI Visibility Report</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">
            {client.name} &mdash; {period_label} Report
          </h2>
          <p style="margin:0 0 24px;color:#6b7280;font-size:14px;">
            Your monthly AI Visibility Report is attached as a PDF. Open it to review
            your score breakdown, competitor comparison, and recommended actions.
          </p>
          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin-bottom:24px;">
            <p style="margin:0 0 4px;font-size:13px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;">Overall GEO Score</p>
            <p style="margin:0;font-size:28px;font-weight:700;color:#0f172a;">
              {report.overall_score:.0f} / 100
            </p>
            <p style="margin:4px 0 0;font-size:14px;color:#6b7280;">
              Your AI Visibility Score for {period_label}.
            </p>
          </div>
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
