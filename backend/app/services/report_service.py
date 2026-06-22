import html
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import structlog
import resend as resend_module

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.constants import PLATFORM_LABELS

try:
    import weasyprint  # noqa: F401 — used when generating PDF bytes
except (ImportError, OSError):
    # OSError: WeasyPrint imports but can't load GTK/Pango native libs (e.g. bare Windows)
    weasyprint = None  # type: ignore[assignment]

from app.models.client import Client
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.geo_score import GeoScore
from app.models.competitor import Competitor
from app.models.toolkit_files import ToolkitFiles
from app.models.activity_log import ActivityLog
from app.models.report import Report
from app.models.ai_traffic_snapshot import AiTrafficSnapshot
from app.services.scoring_service import get_score_band
from app.services.r2_service import upload_pdf, download_pdf
from app.services.claude_action import get_digest_action
from app.services.claude_client import MODEL_NARRATIVE, anthropic_client
from app.services.share_link_service import get_share_link_url
from app.services.cost_tracker import record_llm_call
from app.services.remediation_service import sync_remediation_items, get_remediation_items
from app.services.revenue_service import estimate_pipeline, PipelineEstimate
from app.core.constants import REMEDIATION_STATUS_LABELS
from app.prompts.report import build_change_narrative

# Max competitor-won topics surfaced in the Content Gaps section.
_CONTENT_GAP_LIMIT = 3
# Max history points plotted in the Score Trend chart (most recent N scans).
_TREND_HISTORY_LIMIT = 6

# Neutral evidence shown for a manual dimension when the admin hasn't written a
# specific note — so "Assessed by SeenBy team" never appears naked (CLAUDE.md §4).
_BRAND_AUTHORITY_FALLBACK = (
    "Based on brand presence, reviews, backlinks and industry recognition."
)
_CONTENT_QUALITY_FALLBACK = (
    "Based on content depth, accuracy, freshness and topical expertise."
)

# Traffic-light badge classes for a remediation status chip in the PDF.
_REMEDIATION_BADGE = {
    "flagged":     "badge-red",
    "in_progress": "badge-yellow",
    "corrected":   "badge-green",
}

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
class ContentGap:
    """A neutral-intent query where a competitor was seen by AI but the client was not.
    status tracks the remediation loop (flagged/in_progress/corrected)."""
    query_text: str
    platform: str
    competitors_seen: list[str]
    status: str = "flagged"
    status_label: str = "Flagged"


@dataclass
class HallucinationLine:
    """An inaccurate AI answer about the client, with its remediation status."""
    platform: str
    query_text: str
    status: str = "flagged"
    status_label: str = "Flagged"


@dataclass
class TrendPoint:
    label: str
    score: float
    color: str


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
    brand_authority_evidence: str | None = None
    content_quality_evidence: str | None = None
    ai_visitors_current: int | None = None
    ai_visitors_prev: int | None = None
    platform_breakdown: dict | None = None
    change_narrative: str = ""
    score_history: list[TrendPoint] = field(default_factory=list)
    hallucinations: list[HallucinationLine] = field(default_factory=list)
    content_gaps: list[ContentGap] = field(default_factory=list)
    # Number of previously-lost questions now won back this period (proof of progress).
    gaps_won_back: int = 0
    # AI-referral pipeline estimate for the latest month, or None when unconfigured.
    pipeline: PipelineEstimate | None = None


def _compute_trend(current: float, prev: float | None) -> str:
    if prev is None:
        return "first"
    if current > prev + 0.5:
        return "up"
    if current < prev - 0.5:
        return "down"
    return "flat"


def _fallback_narrative(data: "ReportData") -> str:
    """Deterministic narrative used for first reports or when Claude is unavailable."""
    if data.trend == "first":
        return (
            f"This is {data.period_label}'s first AI Visibility Report. "
            f"Your brand was seen by AI in {data.seen_count} of {data.total_count} tracked queries, "
            f"giving an overall score of {data.overall_score:.0f}. "
            f"We'll track how this changes month over month from here."
        )
    if data.prev_overall_score is None:
        delta_sentence = "Your overall score is holding steady this month."
    else:
        diff = data.overall_score - data.prev_overall_score
        if diff > 0.5:
            delta_sentence = (
                f"Your overall score rose from {data.prev_overall_score:.0f} to {data.overall_score:.0f} this month."
            )
        elif diff < -0.5:
            delta_sentence = (
                f"Your overall score slipped from {data.prev_overall_score:.0f} to {data.overall_score:.0f} this month."
            )
        else:
            delta_sentence = f"Your overall score held steady at {data.overall_score:.0f} this month."
    return (
        f"{delta_sentence} Your brand was seen by AI in {data.seen_count} of "
        f"{data.total_count} tracked queries during {data.period_label}."
    )


def _generate_change_narrative(
    data: "ReportData",
    client_id: uuid.UUID | None = None,
    db: Session | None = None,
) -> str:
    """Claude-written 2-3 sentence "what changed this month" summary. Falls back
    to a deterministic sentence on first report or any API failure — never raises."""
    if data.trend == "first" or data.prev_overall_score is None:
        return _fallback_narrative(data)

    try:
        response = anthropic_client().messages.create(
            model=MODEL_NARRATIVE,
            max_tokens=300,
            messages=[{"role": "user", "content": build_change_narrative(data)}],
        )
        record_llm_call(
            service="report_narrative",
            model=MODEL_NARRATIVE,
            response=response,
            client_id=client_id,
            db=db,
        )
        text = response.content[0].text.strip()
        return text or _fallback_narrative(data)
    except Exception:
        logger.warning("change_narrative_generation_failed")
        return _fallback_narrative(data)


def _score_css(color: str) -> str:
    return {"green": "score-green", "yellow": "score-yellow", "red": "score-red"}.get(color, "score-red")


def _verified_badge(verified: bool) -> str:
    return '<span class="badge-green">Verified</span>' if verified else '<span class="badge-red">Not Verified</span>'


_TREND_HEX = {"green": "#16a34a", "yellow": "#ca8a04", "red": "#dc2626"}


def _build_trend_svg(history: list["TrendPoint"]) -> str:
    """Inline SVG bar chart of overall score over the last few scans.

    WeasyPrint renders inline SVG, so this needs no JS or external image. Bars
    are coloured by each score's traffic-light band; value sits above, the scan
    date below.
    """
    width, height = 500, 200
    pad_top, pad_bottom = 28, 28
    plot_h = height - pad_top - pad_bottom
    n = len(history)
    slot = width / n
    bar_w = min(56.0, slot * 0.55)

    bars: list[str] = []
    for i, pt in enumerate(history):
        cx = slot * i + slot / 2
        bar_h = max(2.0, (pt.score / 100.0) * plot_h)
        y = pad_top + (plot_h - bar_h)
        hex_color = _TREND_HEX.get(pt.color, "#dc2626")
        bars.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" rx="4" fill="{hex_color}" />'
            f'<text x="{cx:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-size="13" font-weight="700" fill="#0f172a">{pt.score:.0f}</text>'
            f'<text x="{cx:.1f}" y="{height - 8:.1f}" text-anchor="middle" '
            f'font-size="10" fill="#64748b">{html.escape(pt.label)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
        f'<line x1="0" y1="{height - pad_bottom}" x2="{width}" '
        f'y2="{height - pad_bottom}" stroke="#e2e8f0" stroke-width="1" />'
        f'{"".join(bars)}</svg>'
    )


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

    current_period = now.date().replace(day=1)
    prev_period = (current_period - timedelta(days=1)).replace(day=1)
    current_traffic = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client.id, AiTrafficSnapshot.period == current_period)
        .first()
    )
    prev_traffic = (
        db.query(AiTrafficSnapshot)
        .filter(AiTrafficSnapshot.client_id == client.id, AiTrafficSnapshot.period == prev_period)
        .first()
    )

    # ── Score Trend — last N computed scores, oldest first ──────────────────
    history_scores = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(desc(GeoScore.computed_at))
        .limit(_TREND_HISTORY_LIMIT)
        .all()
    )
    score_history = [
        TrendPoint(
            label=f"{gs.computed_at.day} {gs.computed_at.strftime('%b')}",
            score=gs.overall_score,
            color=get_score_band(gs.overall_score)[1],
        )
        for gs in reversed(history_scores)
    ]

    # ── Remediation loop — tracked hallucinations & competitor-won queries with
    #    their Flagged → In progress → Corrected status. Persisted across scans so
    #    the report proves progress, not just status. Client-safe: only the
    #    question, platform and competitor names — never the raw AI response (§8).
    sync_remediation_items(client.id, db)
    remediation = get_remediation_items(client.id, db, include_corrected=True)

    hallucinations = [
        HallucinationLine(
            platform=PLATFORM_LABELS.get(i.platform, i.platform.title()) if i.platform else "AI platforms",
            query_text=i.label,
            status=i.status,
            status_label=REMEDIATION_STATUS_LABELS.get(i.status, i.status.title()),
        )
        for i in remediation if i.item_type == "hallucination"
    ]

    gap_items = [i for i in remediation if i.item_type == "content_gap"]
    gaps_won_back = sum(1 for i in gap_items if i.status == "corrected")
    # The "winning here" table lists only still-open gaps; won-back ones are
    # surfaced separately as proof, not under a "competitors are winning" heading.
    content_gaps = [
        ContentGap(
            query_text=i.label,
            platform=PLATFORM_LABELS.get(i.platform, i.platform.title()) if i.platform else "—",
            competitors_seen=[s.strip() for s in (i.detail or "").split(",") if s.strip()],
            status=i.status,
            status_label=REMEDIATION_STATUS_LABELS.get(i.status, i.status.title()),
        )
        for i in gap_items if i.status != "corrected"
    ][:_CONTENT_GAP_LIMIT]

    pipeline = estimate_pipeline(
        current_traffic.ai_visitors if current_traffic else None, client
    )

    data = ReportData(
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
        brand_authority_evidence=client.brand_authority_evidence,
        content_quality_evidence=client.content_quality_evidence,
        ai_visitors_current=current_traffic.ai_visitors if current_traffic else None,
        ai_visitors_prev=prev_traffic.ai_visitors if prev_traffic else None,
        platform_breakdown=current_gs.platform_breakdown,
        score_history=score_history,
        hallucinations=hallucinations,
        content_gaps=content_gaps,
        gaps_won_back=gaps_won_back,
        pipeline=pipeline,
    )
    data.change_narrative = _generate_change_narrative(data, client_id=client.id, db=db)
    return data


def _build_report_html(client: Client, data: ReportData) -> str:
    _, ai_color = get_score_band(data.ai_citability)
    _, ba_color = get_score_band(data.brand_authority)
    _, cq_color = get_score_band(data.content_quality)
    _, tf_color = get_score_band(data.technical_foundations)
    _, sd_color = get_score_band(data.structured_data)

    # Escape every free-text field (client name, admin evidence notes, Claude
    # narrative/recommendation, competitor names) before it enters the report
    # HTML — a stray '<' or '&' in an evidence note must not break the PDF.
    safe_name = html.escape(client.name)
    safe_recommendation = html.escape(data.recommendation or "")
    safe_narrative = html.escape(data.change_narrative or "")
    # A manual dimension's evidence note must never be empty under the "Assessed
    # by SeenBy team" label — fall back to a neutral methodology line (CLAUDE.md §4).
    safe_ba_evidence = (
        html.escape(data.brand_authority_evidence)
        if data.brand_authority_evidence and data.brand_authority_evidence.strip()
        else _BRAND_AUTHORITY_FALLBACK
    )
    safe_cq_evidence = (
        html.escape(data.content_quality_evidence)
        if data.content_quality_evidence and data.content_quality_evidence.strip()
        else _CONTENT_QUALITY_FALLBACK
    )

    trend_colors = {"up": "#16a34a", "down": "#dc2626", "flat": "#6b7280", "first": "#6b7280"}
    trend_color = trend_colors[data.trend]
    if data.trend == "up":
        trend_msg = f"&#8593; Score improved from {data.prev_overall_score:.0f} to {data.overall_score:.0f}"
    elif data.trend == "down":
        trend_msg = f"&#8595; Score decreased from {data.prev_overall_score:.0f} to {data.overall_score:.0f}"
    elif data.trend == "flat":
        trend_msg = f"&#8594; Score held steady at {data.overall_score:.0f}"
    else:
        trend_msg = "First AI Visibility Report"

    if data.competitors:
        comp_rows = "".join(
            f"""<tr>
              <td>{html.escape(c.name)}</td>
              <td class="{_score_css(get_score_band(c.ai_citability)[1])}">{c.ai_citability:.0f}%</td>
              <td>{"<span class='badge-red'>Winning</span>" if c.is_winning else "<span class='badge-green'>You are ahead</span>"}</td>
            </tr>"""
            for c in data.competitors
        )
    else:
        comp_rows = '<tr><td colspan="3" style="color:#9ca3af;">No competitors tracked yet.</td></tr>'

    # AI Referral Traffic is always shown — it's the one section that ties AI
    # visibility to business value. Degrades to an explicit "tracking begins"
    # state rather than vanishing, and adds an RM pipeline estimate when the
    # client's deal value is configured.
    if data.ai_visitors_current is not None:
        if data.ai_visitors_prev:
            pct = (data.ai_visitors_current - data.ai_visitors_prev) / data.ai_visitors_prev * 100
            change_label = f"{'&#8593;' if pct >= 0 else '&#8595;'} {pct:+.0f}% vs last month"
        elif data.ai_visitors_current:
            change_label = "New vs last month"
        else:
            change_label = "No change vs last month"
        visitor_stat = f"""
  <div class="stat-box">
    <div class="stat-label">AI Visitors This Month</div>
    <div class="stat-value">{data.ai_visitors_current:,}</div>
    <div class="stat-sub">
      Visitors arriving via ChatGPT, Perplexity, Gemini and Claude &mdash; {change_label}
    </div>
  </div>"""
    else:
        visitor_stat = """
  <div class="stat-box">
    <div class="stat-label">AI Visitors This Month</div>
    <div class="stat-value" style="font-size:16pt;color:#64748b;">Tracking begins soon</div>
    <div class="stat-sub">
      We&rsquo;re connecting your analytics to measure visitors arriving via
      ChatGPT, Perplexity, Gemini and Claude.
    </div>
  </div>"""

    if data.pipeline is not None:
        p = data.pipeline
        pipeline_stat = f"""
  <div class="stat-box" style="background:#f0f9ff;border-color:#bae6fd;">
    <div class="stat-label">Estimated Pipeline From AI This Month</div>
    <div class="stat-value">RM {p.est_pipeline_rm:,}</div>
    <div class="stat-sub">
      &asymp; {p.ai_visitors:,} AI visitors &rarr; ~{p.est_leads:,} leads &rarr;
      <strong>RM {p.est_pipeline_rm:,}</strong> in pipeline, with an estimated
      <strong>RM {p.est_won_rm:,}</strong> won at your {p.lead_to_customer_pct}% close rate.
      <br><span style="color:#94a3b8;">Estimate based on RM {p.avg_deal_value_rm:,} average deal value
      and a {p.visitor_to_lead_pct}% visitor-to-lead rate.</span>
    </div>
  </div>"""
    else:
        pipeline_stat = ""

    traffic_section = f"""
  <h2>AI Referral Traffic</h2>{visitor_stat}{pipeline_stat}
"""

    if data.platform_breakdown:
        platform_rows = "".join(
            f"""<tr>
              <td>{PLATFORM_LABELS.get(platform, platform.title())}</td>
              <td class="{_score_css(get_score_band(entry.get('visibility', 0.0))[1])}">{entry.get('visibility', 0.0):.0f}%</td>
              <td>{"Seen by AI" if entry.get('detected', 0) > 0 else "Not seen by AI"}</td>
            </tr>"""
            if entry.get("status") == "ok"
            else f"""<tr>
              <td>{PLATFORM_LABELS.get(platform, platform.title())}</td>
              <td style="color:#9ca3af;">&mdash;</td>
              <td style="color:#9ca3af;">Platform unavailable this scan</td>
            </tr>"""
            for platform, entry in data.platform_breakdown.items()
        )
        platform_section = f"""
  <h2>Seen by AI &mdash; Platform Breakdown</h2>
  <table>
    <thead><tr><th>Platform</th><th>Visibility Frequency</th><th>Status</th></tr></thead>
    <tbody>{platform_rows}</tbody>
  </table>
"""
    else:
        platform_section = ""

    # ── Score Trend chart — needs at least two scans to show movement ────────
    if len(data.score_history) >= 2:
        trend_section = f"""
  <h2>Score Trend</h2>
  <p style="font-size:10pt;color:#64748b;margin:0 0 8px;">
    Your overall GEO Score across recent scans.
  </p>
  <div class="stat-box" style="padding:12px 16px;">{_build_trend_svg(data.score_history)}</div>
"""
    else:
        trend_section = ""

    # ── Content Gaps — competitor-won queries, with remediation status. Shows a
    #    "won back" proof line when previously-lost questions are now corrected. ─
    won_back_note = ""
    if data.gaps_won_back:
        won_back_note = (
            f"""<p style="font-size:10pt;color:#166534;margin:0 0 10px;font-weight:600;">"""
            f"""&#10003; {data.gaps_won_back} previously-lost question"""
            f"""{"s" if data.gaps_won_back != 1 else ""} won back this period &mdash; """
            f"""{safe_name} is now seen by AI where a competitor used to win.</p>"""
        )
    if data.content_gaps or data.gaps_won_back:
        gap_rows = "".join(
            f"""<tr>
              <td>{html.escape(g.query_text)}</td>
              <td>{html.escape(", ".join(g.competitors_seen)) or "&mdash;"}</td>
              <td>{html.escape(g.platform)}</td>
              <td><span class="{_REMEDIATION_BADGE.get(g.status, 'badge-red')}">{html.escape(g.status_label)}</span></td>
            </tr>"""
            for g in data.content_gaps
        )
        gap_table = f"""
  <table>
    <thead><tr><th>When people ask AI</th><th>AI recommends</th><th>Platform</th><th>Status</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table>""" if data.content_gaps else ""
        open_count = len(data.content_gaps)
        intro = (
            f"""{open_count} open question{"s" if open_count != 1 else ""} where AI recommends a competitor but not {safe_name}. """
            f"""We&rsquo;re working each one back."""
            if open_count else
            f"""No open competitor-won questions this period &mdash; nice work."""
        )
        content_gap_section = f"""
  <h2>Your Competitors Are Winning Here</h2>
  {won_back_note}
  <p style="font-size:10pt;color:#64748b;margin:0 0 10px;">{intro}</p>
  {gap_table}
"""
    else:
        content_gap_section = ""

    # ── Hallucinations — inaccurate AI answers, with remediation status. ──────
    if data.hallucinations:
        hallu_rows = "".join(
            f"""<tr>
              <td>{html.escape(h.platform)}</td>
              <td>{html.escape(h.query_text)}</td>
              <td><span class="{_REMEDIATION_BADGE.get(h.status, 'badge-red')}">{html.escape(h.status_label)}</span></td>
            </tr>"""
            for h in data.hallucinations
        )
        hallucination_section = f"""
  <h2>Inaccurate AI Answers Flagged</h2>
  <p style="font-size:10pt;color:#64748b;margin:0 0 10px;">
    Where AI platforms gave inaccurate information about {safe_name}, our team flags it and works to
    correct the record. Status shows where each fix stands.
  </p>
  <table>
    <thead><tr><th>Platform</th><th>Question asked</th><th>Status</th></tr></thead>
    <tbody>{hallu_rows}</tbody>
  </table>
"""
    else:
        hallucination_section = ""

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
    <div class="cover-client">{safe_name}</div>
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
{trend_section}
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
        <td>Based on public evidence · Reviewed by SeenBy<div class="manual-note">Manual assessment{f": {safe_ba_evidence}" if safe_ba_evidence else ""}</div></td>
      </tr>
      <tr>
        <td>Content Quality</td>
        <td class="{_score_css(cq_color)}">{data.content_quality:.0f}</td>
        <td>20%</td><td>{data.content_quality * 0.20:.1f}</td>
        <td>Based on public evidence · Reviewed by SeenBy<div class="manual-note">Manual assessment{f": {safe_cq_evidence}" if safe_cq_evidence else ""}</div></td>
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
      {safe_name} was seen by AI in {data.seen_count} out of {data.total_count} queries this period.
    </div>
  </div>
{platform_section}{traffic_section}
  <h2>Competitor Comparison</h2>
  <table>
    <thead><tr><th>Name</th><th>AI Citability</th><th>Status</th></tr></thead>
    <tbody>
      <tr>
        <td><strong>{safe_name} (You)</strong></td>
        <td class="{_score_css(ai_color)}">{data.ai_citability:.0f}%</td>
        <td>&mdash;</td>
      </tr>
      {comp_rows}
    </tbody>
  </table>
{content_gap_section}{hallucination_section}
  <h2>AI Readiness Toolkit</h2>
  <table>
    <thead><tr><th>File</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>llms.txt</td><td>{_verified_badge(data.llms_verified)}</td></tr>
      <tr><td>schema.json (JSON-LD)</td><td>{_verified_badge(data.schema_verified)}</td></tr>
      <tr><td>robots.txt (AI Bots)</td><td>{_verified_badge(data.robots_verified)}</td></tr>
    </tbody>
  </table>

  {f'''<h2>What Changed This Month</h2>
  <div class="rec-box">
    <p style="margin:0;font-size:11pt;color:#0c4a6e;">{safe_narrative}</p>
  </div>''' if safe_narrative else ""}

  <h2>Recommended Action</h2>
  <div class="rec-box">
    <p style="margin:0;font-size:11pt;color:#0c4a6e;">{safe_recommendation}</p>
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
    # Monthly PDF reports are a paying-client deliverable; the client view also
    # gates the /reports tab behind non-prospect. Never auto- or manually
    # generate one for a prospect.
    if client.is_prospect:
        logger.info("report_skipped_prospect", client_id=str(client_id))
        return None

    data = _gather_report_data(client, db)
    if data is None:
        logger.warning("no_scan_data_for_report", client_id=str(client_id))
        return None

    if weasyprint is None:
        # The import guard sets weasyprint=None when GTK/Pango native libs are
        # unavailable (e.g. a bare Windows box). Fail loudly instead of an opaque
        # AttributeError so the cause — a missing system dependency — is clear.
        raise RuntimeError(
            "WeasyPrint native libraries are not available — cannot render PDF reports "
            "on this host. Install the GTK/Pango runtime or generate reports on a worker "
            "that has it."
        )

    report_html = _build_report_html(client, data)
    pdf_bytes = weasyprint.HTML(string=report_html).write_pdf()

    key = f"reports/{client_id}/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    r2_url = upload_pdf(key, pdf_bytes)

    report = Report(
        client_id=client_id,
        r2_key=key,
        r2_url=r2_url,
        period_start=data.period_start,
        period_end=data.period_end,
        overall_score=data.overall_score,
        change_narrative=data.change_narrative or None,
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
        "attachments": [{"filename": filename, "content": pdf_bytes}],
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
    safe_name = html.escape(client.name)
    view_url = get_share_link_url(client)
    dashboard_button = ""
    if view_url:
        dashboard_button = f"""
          <div style="text-align:center;margin:24px 0 0;">
            <a href="{view_url}"
               style="display:inline-block;background:#0f172a;color:#ffffff;
                      font-size:14px;font-weight:600;text-decoration:none;
                      padding:12px 28px;border-radius:6px;">
              View Your Live Dashboard
            </a>
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
          <p style="margin:4px 0 0;color:#94a3b8;font-size:13px;">Monthly AI Visibility Report</p>
        </td></tr>
        <tr><td style="padding:32px;">
          <h2 style="margin:0 0 8px;font-size:18px;color:#0f172a;">
            {safe_name} &mdash; {period_label} Report
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
