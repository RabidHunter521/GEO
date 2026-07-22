import html
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from app.core.time import utcnow

if TYPE_CHECKING:
    # Type-only import — the runtime import stays lazy inside _gather_report_data
    # to avoid pulling the proof-card chain in at module load.
    from app.services.proof_card_service import ProofCard
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
from app.services.revenue_service import estimate_pipeline, PipelineEstimate, estimate_value_at_risk, ValueAtRisk
from app.services.causality_service import compute_causal_trend
from app.services.ga4_traffic_service import format_breakdown
from app.services.headline_battle_service import select_headline_battle
from app.services.benchmark_service import compute_industry_benchmark
from app.core.constants import REMEDIATION_STATUS_LABELS
from app.prompts.report import build_change_narrative
from app.services.language_sanitizer import sanitize_text as _sanitize_text

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

# ── CSS ─────────────────────────────────────────────────────────────────────

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

/* Named page for cover — no running header or footer */
@page cover-page {
  size: A4;
  margin: 2cm;
}

/* Default page — running header and footer in margin boxes */
@page {
  size: A4;
  margin-top: 3cm;
  margin-bottom: 2.2cm;
  margin-left: 2cm;
  margin-right: 2cm;

  @top-left {
    background-color: #070d1a;
    color: #ffffff;
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 8.5pt;
    font-weight: 600;
    content: "SeenBy";
    padding: 0 2cm;
    vertical-align: middle;
    width: 40%;
  }
  @top-right {
    background-color: #070d1a;
    color: #94a3b8;
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 8.5pt;
    content: string(report-page-header);
    padding: 0 2cm;
    vertical-align: middle;
    text-align: right;
    width: 60%;
  }
  @bottom-left {
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 8pt;
    color: #94a3b8;
    content: "Confidential";
    padding: 0 2cm;
    vertical-align: middle;
    border-top: 1px solid #e2e8f0;
  }
  @bottom-right {
    font-family: 'Inter', -apple-system, sans-serif;
    font-size: 8pt;
    color: #94a3b8;
    content: "Page " counter(page) " of " counter(pages);
    padding: 0 2cm;
    vertical-align: middle;
    text-align: right;
    border-top: 1px solid #e2e8f0;
  }
}

* { box-sizing: border-box; }

/* Hidden element whose text content is captured for the @top-right margin box */
.report-page-header-string {
  string-set: report-page-header content();
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  color: #0f172a;
  font-size: 10pt;
  line-height: 1.6;
  margin: 0;
  background: #ffffff;
}

/* ── Cover ─────────────────────────────────────────────────────────── */
.page-break { page-break-after: always; }

.cover {
  page: cover-page;
  background: #070d1a;
  color: #ffffff;
  padding: 48px 0 44px;
}
.cover-logo {
  font-size: 20pt;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}
.cover-rule {
  border: none;
  border-top: 3px solid #2563eb;
  margin: 0 0 8px;
}
.cover-tagline {
  font-size: 8pt;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 600;
  margin-bottom: 44px;
}
.cover-report-type {
  font-size: 8.5pt;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 600;
  margin-bottom: 8px;
}
.cover-client {
  font-size: 26pt;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin-bottom: 4px;
}
.cover-period {
  font-size: 11pt;
  color: #94a3b8;
}
.cover-gauge-wrap { text-align: center; margin: 44px 0 0; }
.cover-score-number {
  font-size: 52pt;
  font-weight: 700;
  color: #ffffff;
  line-height: 1;
  text-align: center;
  margin: 10px 0 4px;
  letter-spacing: -0.03em;
}
.cover-score-label {
  font-size: 9pt;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  text-align: center;
  font-weight: 600;
}
.cover-narrative {
  max-width: 440px;
  margin: 36px auto 0;
  font-size: 10.5pt;
  line-height: 1.7;
  color: #cbd5e1;
  text-align: center;
  font-style: italic;
}
.cover-footer {
  border-top: 1px solid #1e2d4a;
  padding-top: 14px;
  font-size: 8pt;
  color: #475569;
  margin-top: 56px;
}

/* ── Section headers ────────────────────────────────────────────────── */
h2 {
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #0f172a;
  border-left: 3px solid #2563eb;
  border-bottom: none;
  padding: 0 0 0 10px;
  margin-top: 28px;
  margin-bottom: 14px;
}

/* ── Tables ─────────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
thead tr { background: #070d1a; }
th {
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
  color: #ffffff;
  font-size: 8pt;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border: none;
}
tbody tr:nth-child(even) { background: #f8fafc; }
tbody tr:nth-child(odd)  { background: #ffffff; }
td { padding: 10px 14px; border-bottom: 1px solid #f1f5f9; font-size: 10pt; }
td:first-child { font-weight: 600; }

.score-green  { color: #059669; font-weight: 700; }
.score-yellow { color: #d97706; font-weight: 700; }
.score-red    { color: #dc2626; font-weight: 700; }

.badge-green  { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 4px; font-size: 9pt; font-weight: 600; }
.badge-yellow { background: #fef9c3; color: #854d0e; padding: 2px 8px; border-radius: 4px; font-size: 9pt; font-weight: 600; }
.badge-red    { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 9pt; font-weight: 600; }

/* ── Standard stat block (typography-only, no grey box) ─────────────── */
.stat-block { padding: 14px 0 10px; margin-bottom: 14px; border-top: 1px solid #e2e8f0; }
.stat-label { font-size: 8pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; margin-bottom: 4px; }
.stat-value { font-size: 26pt; font-weight: 700; color: #0f172a; line-height: 1.1; margin-bottom: 4px; }
.stat-sub   { font-size: 9.5pt; color: #64748b; }

/* ── Special stat variants ──────────────────────────────────────────── */
.stat-pipeline {
  border-left: 4px solid #0891b2;
  background: #f0f9ff;
  padding: 14px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
}
.stat-atrisk {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 14px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 14px;
}
.stat-battle {
  background: #070d1a;
  color: #ffffff;
  padding: 18px 20px;
  border-radius: 6px;
  margin-bottom: 14px;
}
.stat-battle .stat-label { color: #94a3b8; }
.stat-battle .stat-sub   { color: #cbd5e1; font-size: 10.5pt; line-height: 1.6; }
.battle-move { color: #93c5fd; font-weight: 600; }

/* ── Score breakdown dimension bars ─────────────────────────────────── */
.dim-row { margin-bottom: 18px; }
.dim-top { display: table; width: 100%; margin-bottom: 5px; }
.dim-name { display: table-cell; font-size: 10pt; font-weight: 600; color: #0f172a; }
.dim-right { display: table-cell; text-align: right; white-space: nowrap; padding-left: 12px; }
.dim-score-green  { color: #059669; font-weight: 700; font-size: 10pt; margin-right: 8px; }
.dim-score-yellow { color: #d97706; font-weight: 700; font-size: 10pt; margin-right: 8px; }
.dim-score-red    { color: #dc2626; font-weight: 700; font-size: 10pt; margin-right: 8px; }
.dim-weight { font-size: 9pt; color: #94a3b8; }
.dim-source { font-size: 8.5pt; color: #94a3b8; margin-top: 4px; }
.manual-note { font-size: 8pt; color: #94a3b8; font-style: italic; }

/* ── Proof cards ─────────────────────────────────────────────────────── */
.proof-card { padding: 12px 16px; margin-bottom: 10px; background: #ffffff; border-radius: 0 4px 4px 0; }
.proof-win  { border-left: 4px solid #059669; }
.proof-loss { border-left: 4px solid #d97706; }
.proof-tag      { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }
.proof-tag-win  { color: #059669; }
.proof-tag-loss { color: #d97706; }
.proof-quote    { font-style: italic; margin: 0; font-size: 10.5pt; color: #1e293b; }

/* ── Recommended action ──────────────────────────────────────────────── */
.rec-box   { border-left: 4px solid #2563eb; background: #eff6ff; padding: 14px 16px; border-radius: 0 4px 4px 0; }
.rec-label { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #2563eb; display: block; margin-bottom: 6px; }
.rec-body  { margin: 0; font-size: 11pt; color: #1e3a8a; }

/* ── Trend chart container ───────────────────────────────────────────── */
.trend-container { border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; background: #ffffff; margin-bottom: 16px; }

/* ── Misc ────────────────────────────────────────────────────────────── */
.score-trend-line { font-size: 12pt; font-weight: 700; margin-bottom: 14px; }
.won-back-note { font-size: 10pt; color: #166534; font-weight: 600; margin-bottom: 10px; }
.report-footer { margin-top: 40px; font-size: 8pt; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 12px; }
"""


@dataclass
class CompetitorSummary:
    name: str
    ai_citability: float
    is_winning: bool


@dataclass
class ContentGap:
    """A neutral-intent query where a competitor was seen by AI but the client was not.
    status tracks the remediation loop (flagged/in_progress/corrected)"""
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
    # Formatted per-platform split ("ChatGPT 140 · Perplexity 60") — GA4 months only.
    ai_breakdown: str | None = None
    platform_breakdown: dict | None = None
    change_narrative: str = ""
    score_history: list[TrendPoint] = field(default_factory=list)
    hallucinations: list[HallucinationLine] = field(default_factory=list)
    content_gaps: list[ContentGap] = field(default_factory=list)
    # Number of previously-lost questions now won back this period (proof of progress).
    gaps_won_back: int = 0
    # AI-referral pipeline estimate for the latest month, or None when unconfigured.
    pipeline: PipelineEstimate | None = None
    # Pipeline estimated lost to AI invisibility this month, or None when unconfigured.
    value_at_risk: ValueAtRisk | None = None
    # The single 'battle to win next' (rival + lost query + one move), or None.
    headline_battle: object | None = None
    # Causal proof (first vs latest scan carrying benchmark data), or None
    # when fewer than 2 scans have "left alone" points — section omitted.
    causal_optimized_then: float | None = None
    causal_optimized_now: float | None = None
    causal_control_then: float | None = None
    causal_control_now: float | None = None
    # Query-level changes vs previous scan — used by the narrative prompt so Claude
    # can name specific questions that moved rather than just quoting aggregate numbers.
    newly_seen_queries: list[str] = field(default_factory=list)
    newly_lost_queries: list[str] = field(default_factory=list)
    # Verbatim AI proof cards for the latest scan (rival named — private PDF).
    proof_cards: list["ProofCard"] = field(default_factory=list)


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


_TREND_HEX = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}


def _build_trend_svg(history: list["TrendPoint"]) -> str:
    """Inline SVG bar chart of overall score over the last few scans."""
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
            f'height="{bar_h:.1f}" rx="6" fill="{hex_color}" />'
            f'<text x="{cx:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'font-size="13" font-weight="700" fill="#0f172a">{pt.score:.0f}</text>'
            f'<text x="{cx:.1f}" y="{height - 8:.1f}" text-anchor="middle" '
            f'font-size="10" fill="#94a3b8">{html.escape(pt.label)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
        f'<line x1="0" y1="{height - pad_bottom}" x2="{width}" '
        f'y2="{height - pad_bottom}" stroke="#e2e8f0" stroke-width="1" />'
        f'{"".join(bars)}</svg>'
    )


def _build_gauge_svg(score: float) -> str:
    """Semicircle gauge for the cover page.

    Score 0-100 maps to left (0) → right (100) arc over the top.
    The arc uses stroke on a path so no fill geometry is needed.
    """
    display_score = max(1.0, min(100.0, score))
    if score >= 70:
        color = "#059669"
    elif score >= 30:
        color = "#d97706"
    else:
        color = "#dc2626"
    # Center (120, 120), radius 100. Left endpoint (20, 120), right (220, 120).
    # Angle: π at score=0 (left), 0 at score=100 (right).
    angle = math.pi - (display_score / 100.0) * math.pi
    ex = 120.0 + 100.0 * math.cos(angle)
    ey = 120.0 - 100.0 * math.sin(angle)
    # large_arc = 0 always: the filled portion never exceeds 180°.
    return (
        f'<svg viewBox="0 0 240 130" width="240" height="130" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GEO Score gauge">'
        f'<path d="M 20,120 A 100,100 0 0,1 220,120" '
        f'stroke="#1e2d4a" stroke-width="20" fill="none" stroke-linecap="round"/>'
        f'<path d="M 20,120 A 100,100 0 0,1 {ex:.2f},{ey:.2f}" '
        f'stroke="{color}" stroke-width="20" fill="none" stroke-linecap="round"/>'
        f'</svg>'
    )


def _build_dim_bar_svg(score: float, color: str) -> str:
    """Horizontal progress bar for a single score dimension row."""
    hex_color = _TREND_HEX.get(color, "#dc2626")
    fill_w = max(0.0, min(400.0, (score / 100.0) * 400.0))
    return (
        f'<svg viewBox="0 0 400 10" width="100%" height="10" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="0" y="0" width="400" height="10" rx="5" fill="#e2e8f0"/>'
        f'<rect x="0" y="0" width="{fill_w:.1f}" height="10" rx="5" fill="{hex_color}"/>'
        f'</svg>'
    )


def _build_dim_bars_html(data: "ReportData") -> str:
    """Score breakdown — one visual bar row per dimension, replaces the old 5-col table."""
    _, ai_color = get_score_band(data.ai_citability)
    _, ba_color = get_score_band(data.brand_authority)
    _, cq_color = get_score_band(data.content_quality)
    _, tf_color = get_score_band(data.technical_foundations)
    _, sd_color = get_score_band(data.structured_data)

    ba_note = (
        _sanitize_text(data.brand_authority_evidence)
        if data.brand_authority_evidence and data.brand_authority_evidence.strip()
        else _BRAND_AUTHORITY_FALLBACK
    )
    cq_note = (
        _sanitize_text(data.content_quality_evidence)
        if data.content_quality_evidence and data.content_quality_evidence.strip()
        else _CONTENT_QUALITY_FALLBACK
    )

    def _dim(name: str, score: float, color: str, weight: str, source: str, note: str = "") -> str:
        bar = _build_dim_bar_svg(score, color)
        note_html = f'<br><span class="manual-note">{html.escape(note)}</span>' if note else ""
        return (
            f'<div class="dim-row">'
            f'<div class="dim-top">'
            f'<div class="dim-name">{html.escape(name)}</div>'
            f'<div class="dim-right">'
            f'<span class="dim-score-{color}">{score:.0f}</span>'
            f'<span class="dim-weight">{html.escape(weight)}</span>'
            f'</div></div>'
            f'{bar}'
            f'<div class="dim-source">{html.escape(source)}{note_html}</div>'
            f'</div>'
        )

    return (
        _dim("AI Citability", data.ai_citability, ai_color, "40%",
             "Automatic — Scan engine")
        + _dim("Brand Authority", data.brand_authority, ba_color, "20%",
               "Based on public evidence · Reviewed by SeenBy", ba_note)
        + _dim("Content Quality", data.content_quality, cq_color, "20%",
               "Based on public evidence · Reviewed by SeenBy", cq_note)
        + _dim("Technical Foundations", data.technical_foundations, tf_color, "10%",
               "Automatic — Toolkit verified")
        + _dim("Structured Data", data.structured_data, sd_color, "10%",
               "Automatic — Toolkit verified")
    )


def _gather_report_data(client: Client, db: Session) -> ReportData | None:
    since = utcnow() - timedelta(days=30)

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
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )
    seen_count = sum(1 for r in client_results if r.brand_detected)
    total_count = len(client_results)

    # Identify which specific queries changed detection status vs the previous scan.
    # Only consider queries that ran in both scans to avoid new/removed query noise.
    newly_seen_queries: list[str] = []
    newly_lost_queries: list[str] = []
    if prev_scan:
        prev_client_results = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == prev_scan.id,
                ScanQueryResult.competitor_id.is_(None),
                ScanQueryResult.is_control.is_(False),
            )
            .all()
        )
        prev_by_query = {r.query_text: r.brand_detected for r in prev_client_results}
        newly_seen_queries = [
            r.query_text for r in client_results
            if r.query_text in prev_by_query
            and r.brand_detected
            and not prev_by_query[r.query_text]
        ][:3]
        newly_lost_queries = [
            r.query_text for r in client_results
            if r.query_text in prev_by_query
            and not r.brand_detected
            and prev_by_query[r.query_text]
        ][:3]

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

    now = utcnow()

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
    value_at_risk = estimate_value_at_risk(
        current_traffic.ai_visitors if current_traffic else None,
        (current_gs.ai_citability / 100.0) if current_gs else None,
        client,
    )
    headline_battle = select_headline_battle(client.id, db)

    # Causal proof: first vs latest scan carrying "left alone" benchmark data.
    causal = compute_causal_trend(client.id, db)
    causal_points = [p for p in causal.points if p.control_frequency is not None]
    causal_then = causal_points[0] if len(causal_points) >= 2 else None
    causal_now = causal_points[-1] if len(causal_points) >= 2 else None

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
        ai_breakdown=format_breakdown(current_traffic.breakdown) if current_traffic else None,
        platform_breakdown=current_gs.platform_breakdown,
        score_history=score_history,
        hallucinations=hallucinations,
        content_gaps=content_gaps,
        gaps_won_back=gaps_won_back,
        pipeline=pipeline,
        value_at_risk=value_at_risk,
        headline_battle=headline_battle,
        newly_seen_queries=newly_seen_queries,
        newly_lost_queries=newly_lost_queries,
        causal_optimized_then=causal_then.optimized_frequency if causal_then else None,
        causal_optimized_now=causal_now.optimized_frequency if causal_now else None,
        causal_control_then=causal_then.control_frequency if causal_then else None,
        causal_control_now=causal_now.control_frequency if causal_now else None,
    )
    from app.services.proof_card_service import select_proof_cards
    proof_cards = select_proof_cards(
        [r for r in client_results if not r.hallucination_flagged],
        client.name,
        [c.name for c in competitors_orm],
        win_cap=2,
        loss_cap=1,
        redact_competitors=False,  # private reviewed PDF — name the rival
    )
    data.proof_cards = proof_cards
    data.change_narrative = _generate_change_narrative(data, client_id=client.id, db=db)
    return data


def _build_proof_html(data: ReportData) -> str:
    """Verbatim 'Seen by AI' proof cards — border-left only, no background colour."""
    if not data.proof_cards:
        return ""
    rows = []
    for c in data.proof_cards:
        platform = html.escape(PLATFORM_LABELS.get(c.platform, c.platform.title()))
        quote = html.escape(c.excerpt)
        if c.kind == "win":
            rows.append(
                f'<div class="proof-card proof-win">'
                f'<div class="proof-tag proof-tag-win">Seen by AI &middot; {platform}</div>'
                f'<p class="proof-quote">&ldquo;{quote}&rdquo;</p></div>'
            )
        else:
            rows.append(
                f'<div class="proof-card proof-loss">'
                f'<div class="proof-tag proof-tag-loss">Who {platform} recommended instead</div>'
                f'<p class="proof-quote">&ldquo;{quote}&rdquo;</p></div>'
            )
    return '<h2>What AI Said About You</h2>' + "".join(rows)


def _build_battle_html(data: ReportData) -> str:
    """The single 'battle to win next' section — inverted dark card."""
    if data.headline_battle is None:
        return ""
    b = data.headline_battle
    if b.move_title:
        move_html = (
            f'<span class="battle-move">{html.escape(b.move_title)}</span>'
            + (f' &mdash; {html.escape(b.move_angle)}' if b.move_angle else "")
        )
    else:
        move_html = "The play to flip it is being prepared."
    return (
        f'<h2>The Battle To Win Next</h2>'
        f'<div class="stat-battle">'
        f'<div class="stat-label">Competitive Focus</div>'
        f'<div class="stat-sub">'
        f'Your competitor <strong>{html.escape(b.rival_name)}</strong> is winning'
        f' &ldquo;{html.escape(b.query_text)}&rdquo; on {html.escape(b.platform_label)}'
        f' &mdash; you are not seen by AI there yet.<br>'
        f'<strong>The one move to flip it:</strong> {move_html}'
        f'</div></div>'
    )


def _phrase_change(now: float, then: float) -> str:
    """Direction-honest phrasing — never claims 'up from' on a fall."""
    if now > then:
        return f"seen by AI {now:.0f}% of the time, up from {then:.0f}%"
    if now < then:
        return f"seen by AI {now:.0f}% of the time, down from {then:.0f}%"
    return f"seen by AI {now:.0f}% of the time, unchanged"


def _build_causality_html(data: ReportData) -> str:
    """'Did our work cause this?' — optimized vs left-alone, first vs latest.
    Omitted until two scans carry benchmark data."""
    if data.causal_control_now is None or data.causal_control_then is None:
        return ""
    if data.causal_optimized_now is None or data.causal_optimized_then is None:
        return ""
    worked = _phrase_change(data.causal_optimized_now, data.causal_optimized_then)
    left = _phrase_change(data.causal_control_now, data.causal_control_then)
    return (
        f'<h2>Did Our Work Cause This?</h2>'
        f'<div class="stat-card">'
        f'<div class="stat-sub">'
        f'Queries we worked on: {worked}. '
        f'Queries we left alone: {left}. '
        f'<span style="color:#6b7280;">The queries we deliberately left untouched are the '
        f'benchmark — when only the optimized ones move, the movement is our work.</span>'
        f'</div></div>'
    )


def _build_report_html(client: Client, data: ReportData) -> str:
    _, ai_color = get_score_band(data.ai_citability)

    safe_name = html.escape(client.name)
    safe_recommendation = html.escape(data.recommendation or "")
    safe_narrative = html.escape(data.change_narrative or "")

    trend_colors = {"up": "#059669", "down": "#dc2626", "flat": "#6b7280", "first": "#6b7280"}
    trend_color = trend_colors[data.trend]
    if data.trend == "up":
        trend_msg = f"&#8593; Score improved from {data.prev_overall_score:.0f} to {data.overall_score:.0f}"
    elif data.trend == "down":
        trend_msg = f"&#8595; Score decreased from {data.prev_overall_score:.0f} to {data.overall_score:.0f}"
    elif data.trend == "flat":
        trend_msg = f"&#8594; Score held steady at {data.overall_score:.0f}"
    else:
        trend_msg = "First AI Visibility Report"

    # ── Section 1b: Score Trend chart ──────────────────────────────────────
    if len(data.score_history) >= 2:
        trend_section = (
            f'<h2>Score Trend</h2>'
            f'<p style="font-size:9.5pt;color:#64748b;margin:0 0 8px;">'
            f'Your overall GEO Score across recent scans.</p>'
            f'<div class="trend-container">{_build_trend_svg(data.score_history)}</div>'
        )
    else:
        trend_section = ""

    # ── Section 2: Proof cards ─────────────────────────────────────────────
    proof_section = _build_proof_html(data)

    # ── Section 3: Score breakdown bars ───────────────────────────────────
    dim_bars = _build_dim_bars_html(data)

    # ── Section 4b: Platform breakdown ────────────────────────────────────
    if data.platform_breakdown:
        platform_rows = "".join(
            (
                f'<tr><td>{PLATFORM_LABELS.get(platform, platform.title())}</td>'
                f'<td class="{_score_css(get_score_band(entry.get("visibility", 0.0))[1])}">'
                f'{entry.get("visibility", 0.0):.0f}%</td>'
                f'<td>{"Seen by AI" if entry.get("detected", 0) > 0 else "Not seen by AI"}</td></tr>'
            )
            if entry.get("status") == "ok"
            else (
                f'<tr><td>{PLATFORM_LABELS.get(platform, platform.title())}</td>'
                f'<td style="color:#9ca3af;">&mdash;</td>'
                f'<td style="color:#9ca3af;">Platform unavailable this scan</td></tr>'
            )
            for platform, entry in data.platform_breakdown.items()
        )
        platform_section = (
            f'<h2>Seen by AI &mdash; Platform Breakdown</h2>'
            f'<table><thead><tr><th>Platform</th><th>Visibility Frequency</th><th>Status</th></tr></thead>'
            f'<tbody>{platform_rows}</tbody></table>'
        )
    else:
        platform_section = ""

    # ── Section 5: AI Referral Traffic ────────────────────────────────────
    if data.ai_visitors_current is not None:
        if data.ai_visitors_prev:
            pct = (data.ai_visitors_current - data.ai_visitors_prev) / data.ai_visitors_prev * 100
            change_label = f"{'&#8593;' if pct >= 0 else '&#8595;'} {pct:+.0f}% vs last month"
        elif data.ai_visitors_current:
            change_label = "New vs last month"
        else:
            change_label = "No change vs last month"
        breakdown_line = (
            f'<div class="stat-sub">At least: {html.escape(data.ai_breakdown)}</div>'
            if data.ai_breakdown else ""
        )
        visitor_stat = (
            f'<div class="stat-block">'
            f'<div class="stat-label">AI Visitors This Month</div>'
            f'<div class="stat-value">{data.ai_visitors_current:,}</div>'
            f'<div class="stat-sub">Visitors arriving via ChatGPT, Perplexity, Gemini and Claude'
            f' &mdash; {change_label}</div>{breakdown_line}</div>'
        )
    else:
        visitor_stat = (
            '<div class="stat-block">'
            '<div class="stat-label">AI Visitors This Month</div>'
            '<div class="stat-value" style="font-size:16pt;color:#64748b;">Tracking begins soon</div>'
            '<div class="stat-sub">We&rsquo;re connecting your analytics to measure visitors arriving'
            ' via ChatGPT, Perplexity, Gemini and Claude.</div></div>'
        )

    if data.pipeline is not None:
        p = data.pipeline
        pipeline_stat = (
            f'<div class="stat-pipeline">'
            f'<div class="stat-label">Estimated Pipeline From AI This Month</div>'
            f'<div class="stat-value">RM {p.est_pipeline_rm:,}</div>'
            f'<div class="stat-sub">'
            f'&asymp; {p.ai_visitors:,} AI visitors &rarr; ~{p.est_leads:,} leads &rarr;'
            f' <strong>RM {p.est_pipeline_rm:,}</strong> in pipeline, with an estimated'
            f' <strong>RM {p.est_won_rm:,}</strong> won at your {p.lead_to_customer_pct}% close rate.'
            f'<br><span style="color:#94a3b8;">Estimate based on RM {p.avg_deal_value_rm:,}'
            f' average deal value and a {p.visitor_to_lead_pct}% visitor-to-lead rate.</span>'
            f'</div></div>'
        )
    else:
        pipeline_stat = ""

    traffic_section = f'<h2>AI Referral Traffic</h2>{visitor_stat}{pipeline_stat}'

    # ── Section 6: Pipeline at risk (separate section for loss-aversion punch) ─
    if data.value_at_risk is not None:
        r = data.value_at_risk
        at_risk_section = (
            f'<h2>Estimated Pipeline Still On The Table</h2>'
            f'<div class="stat-atrisk">'
            f'<div class="stat-label">Pipeline Still On The Table</div>'
            f'<div class="stat-value">RM {r.missed_pipeline_rm:,}</div>'
            f'<div class="stat-sub">'
            f'&asymp; RM {r.missed_pipeline_rm:,} in pipeline (~{r.missed_leads:,} potential customers)'
            f' is estimated to be <strong>still on the table</strong> because AI does not yet'
            f' recommend you as often as it could.'
            f'<br><span style="color:#94a3b8;">Estimate based on your current AI visibility and'
            f' the same deal value and conversion rates as above.</span>'
            f'</div></div>'
        )
    else:
        at_risk_section = ""

    # ── Section 7: Battle ──────────────────────────────────────────────────
    battle_section = _build_battle_html(data)

    # ── Section 7b: Causal proof (optimized vs left alone) ────────────────
    causality_section = _build_causality_html(data)

    # ── Section 8: Competitor comparison ──────────────────────────────────
    if data.competitors:
        comp_rows = "".join(
            f'<tr><td>{html.escape(c.name)}</td>'
            f'<td class="{_score_css(get_score_band(c.ai_citability)[1])}">{c.ai_citability:.0f}%</td>'
            f'<td>{"<span class=\'badge-red\'>Winning</span>" if c.is_winning else "<span class=\'badge-green\'>You are ahead</span>"}</td></tr>'
            for c in data.competitors
        )
    else:
        comp_rows = '<tr><td colspan="3" style="color:#9ca3af;">No competitors tracked yet.</td></tr>'

    competitor_section = (
        f'<h2>Competitor Comparison</h2>'
        f'<table><thead><tr><th>Name</th><th>AI Citability</th><th>Status</th></tr></thead>'
        f'<tbody>'
        f'<tr><td><strong>{safe_name} (You)</strong></td>'
        f'<td class="{_score_css(ai_color)}">{data.ai_citability:.0f}%</td>'
        f'<td>&mdash;</td></tr>'
        f'{comp_rows}</tbody></table>'
    )

    # ── Section 9: Content gaps ────────────────────────────────────────────
    if data.content_gaps or data.gaps_won_back:
        won_back_note = ""
        if data.gaps_won_back:
            won_back_note = (
                f'<p class="won-back-note">&#10003; {data.gaps_won_back} previously-lost question'
                f'{"s" if data.gaps_won_back != 1 else ""} won back this period &mdash; '
                f'{safe_name} is now seen by AI where a competitor used to win.</p>'
            )
        gap_rows = "".join(
            f'<tr><td>{html.escape(g.query_text)}</td>'
            f'<td>{html.escape(", ".join(g.competitors_seen)) or "&mdash;"}</td>'
            f'<td>{html.escape(g.platform)}</td>'
            f'<td><span class="{_REMEDIATION_BADGE.get(g.status, "badge-red")}">'
            f'{html.escape(g.status_label)}</span></td></tr>'
            for g in data.content_gaps
        )
        gap_table = (
            f'<table><thead><tr>'
            f'<th>When people ask AI</th><th>AI recommends</th><th>Platform</th><th>Status</th>'
            f'</tr></thead><tbody>{gap_rows}</tbody></table>'
        ) if data.content_gaps else ""
        open_count = len(data.content_gaps)
        intro = (
            f'{open_count} open question{"s" if open_count != 1 else ""} where AI recommends'
            f' a competitor but not {safe_name}. We&rsquo;re working each one back.'
            if open_count else
            'No open competitor-won questions this period &mdash; nice work.'
        )
        content_gap_section = (
            f'<h2>Your Competitors Are Winning Here</h2>'
            f'{won_back_note}'
            f'<p style="font-size:10pt;color:#64748b;margin:0 0 10px;">{intro}</p>'
            f'{gap_table}'
        )
    else:
        content_gap_section = ""

    # ── Section 10: Hallucinations ─────────────────────────────────────────
    if data.hallucinations:
        hallu_rows = "".join(
            f'<tr><td>{html.escape(h.platform)}</td>'
            f'<td>{html.escape(h.query_text)}</td>'
            f'<td><span class="{_REMEDIATION_BADGE.get(h.status, "badge-red")}">'
            f'{html.escape(h.status_label)}</span></td></tr>'
            for h in data.hallucinations
        )
        hallucination_section = (
            f'<h2>Inaccurate AI Answers Flagged</h2>'
            f'<p style="font-size:10pt;color:#64748b;margin:0 0 10px;">'
            f'Where AI platforms gave inaccurate information about {safe_name}, our team flags it'
            f' and works to correct the record. Status shows where each fix stands.</p>'
            f'<table><thead><tr><th>Platform</th><th>Question asked</th><th>Status</th></tr></thead>'
            f'<tbody>{hallu_rows}</tbody></table>'
        )
    else:
        hallucination_section = ""

    # ── Gauge SVG + generated date ─────────────────────────────────────────
    gauge_svg = _build_gauge_svg(data.overall_score)
    generated_date = utcnow().strftime("%d %B %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>{_CSS}</style>
</head>
<body>

<!-- Captured by string-set for the @top-right running header -->
<span class="report-page-header-string">{safe_name} &middot; {html.escape(data.period_label)}</span>

<!-- ── COVER ──────────────────────────────────────────────────────── -->
<div class="cover page-break">
  <div class="cover-logo">SeenBy</div>
  <hr class="cover-rule">
  <div class="cover-tagline">AI Visibility Intelligence</div>

  <div class="cover-report-type">Monthly AI Visibility Report</div>
  <div class="cover-client">{safe_name}</div>
  <div class="cover-period">{html.escape(data.period_label)}</div>

  <div class="cover-gauge-wrap">{gauge_svg}</div>
  <div class="cover-score-number">{data.overall_score:.0f}</div>
  <div class="cover-score-label">GEO Score &middot; {data.score_band.title()}</div>

  {f'<p class="cover-narrative">{safe_narrative}</p>' if safe_narrative else ""}

  <div class="cover-footer">
    Report generated {generated_date} &middot; contact@seenby.my
  </div>
</div>

<!-- ── 1: AI VISIBILITY SCORE ────────────────────────────────────── -->
<h2>AI Visibility Score</h2>
<p class="score-trend-line" style="color:{trend_color};">{trend_msg}</p>
<div class="stat-block">
  <div class="stat-label">Overall GEO Score</div>
  <div class="stat-value">{data.overall_score:.0f}<span style="font-size:14pt;color:#64748b;font-weight:400;"> / 100</span></div>
  <div class="stat-sub">{data.score_band.title()} band</div>
</div>
{trend_section}

<!-- ── 2: WHAT AI SAID ABOUT YOU ─────────────────────────────────── -->
{proof_section}

<!-- ── 3: SCORE BREAKDOWN ─────────────────────────────────────────── -->
<h2>Score Breakdown</h2>
{dim_bars}

<!-- ── 4: AI VISIBILITY FREQUENCY + PLATFORM ─────────────────────── -->
<h2>AI Visibility Frequency</h2>
<div class="stat-block">
  <div class="stat-label">Seen by AI</div>
  <div class="stat-value">{data.seen_count}/{data.total_count}</div>
  <div class="stat-sub">{safe_name} was seen by AI in {data.seen_count} out of {data.total_count} queries this period.</div>
</div>
{platform_section}

<!-- ── 5: AI REFERRAL TRAFFIC ─────────────────────────────────────── -->
{traffic_section}

<!-- ── 6: AT RISK ────────────────────────────────────────────────── -->
{at_risk_section}

<!-- ── 7: BATTLE ──────────────────────────────────────────────────── -->
{battle_section}
{causality_section}

<!-- ── 8: COMPETITOR COMPARISON ──────────────────────────────────── -->
{competitor_section}

<!-- ── 9: CONTENT GAPS ────────────────────────────────────────────── -->
{content_gap_section}

<!-- ── 10: HALLUCINATIONS ─────────────────────────────────────────── -->
{hallucination_section}

<!-- ── 11: AI READINESS TOOLKIT ──────────────────────────────────── -->
<h2>AI Readiness Toolkit</h2>
<table>
  <thead><tr><th>File</th><th>Status</th></tr></thead>
  <tbody>
    <tr><td>llms.txt</td><td>{_verified_badge(data.llms_verified)}</td></tr>
    <tr><td>schema.json (JSON-LD)</td><td>{_verified_badge(data.schema_verified)}</td></tr>
    <tr><td>robots.txt (AI Bots)</td><td>{_verified_badge(data.robots_verified)}</td></tr>
  </tbody>
</table>

<!-- ── 12: RECOMMENDED ACTION ────────────────────────────────────── -->
<h2>Recommended Action</h2>
<div class="rec-box">
  <span class="rec-label">Recommended Action</span>
  <p class="rec-body">{safe_recommendation}</p>
</div>

<p class="report-footer">
  This report was generated automatically by SeenBy. Manual dimension scores (Brand Authority,
  Content Quality) are assessed by the SeenBy team. Contact: contact@seenby.my
</p>

</body>
</html>"""


# ── One-page Scorecard ──────────────────────────────────────────────────────

_SCORECARD_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
@page { size: A4; margin: 1.4cm; }
* { box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  color: #0f172a;
  font-size: 11pt;
  line-height: 1.5;
  margin: 0;
}
.sc-top { border-bottom: 3px solid #070d1a; padding-bottom: 10px; margin-bottom: 22px; }
.sc-logo { font-size: 18pt; font-weight: 700; color: #070d1a; letter-spacing: -0.02em; }
.sc-kicker { font-size: 10pt; color: #64748b; }
.sc-client { font-size: 20pt; font-weight: 700; color: #0f172a; margin: 0 0 2px; letter-spacing: -0.02em; }
.sc-score-box {
  background: #070d1a; color: #ffffff; border-radius: 10px;
  padding: 18px 30px; text-align: center;
}
.sc-score-value { font-size: 46pt; font-weight: 700; line-height: 1; letter-spacing: -0.03em; }
.sc-score-label { font-size: 10pt; color: #94a3b8; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.06em; }
.sc-headline { font-size: 17pt; font-weight: 700; color: #0f172a; line-height: 1.3; letter-spacing: -0.01em; }
.sc-benchmark {
  display: inline-block; margin-top: 10px; background: #f0f9ff; color: #0369a1;
  border: 1px solid #bae6fd; border-radius: 999px; padding: 4px 14px;
  font-size: 10pt; font-weight: 600;
}
.sc-section-label {
  font-size: 9pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em;
  font-weight: 700; margin: 24px 0 10px;
  border-left: 3px solid #2563eb; padding-left: 8px;
}
.sc-tile {
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; text-align: center;
}
.sc-tile-name { font-size: 10pt; color: #475569; font-weight: 600; }
.sc-tile-value { font-size: 20pt; font-weight: 700; color: #0f172a; letter-spacing: -0.02em; }
.sc-tile-sub { font-size: 8pt; color: #94a3b8; }
.sc-changed { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 18px; font-style: italic; color: #475569; }
.sc-foot { margin-top: 28px; font-size: 9pt; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 10px; }
"""


def _build_scorecard_html(client: Client, data: ReportData, benchmark) -> str:
    safe_name = html.escape(client.name)
    safe_narrative = html.escape(data.change_narrative or "")
    generated_date = utcnow().strftime("%d %B %Y")

    headline = (
        f"Seen by AI in {data.seen_count} of {data.total_count} buyer questions"
        if data.total_count
        else "Your AI visibility snapshot"
    )
    benchmark_chip = (
        f'<div class="sc-benchmark">Top {benchmark.top_percent}% of '
        f"{html.escape(benchmark.industry)}</div>"
        if benchmark
        else ""
    )

    tiles = ""
    if data.platform_breakdown:
        cells = []
        for platform, entry in data.platform_breakdown.items():
            name = PLATFORM_LABELS.get(platform, platform.title())
            if entry.get("status") == "ok":
                value = f"{entry.get('visibility', 0.0):.0f}%"
                sub = "Seen by AI" if entry.get("detected", 0) > 0 else "Not seen by AI"
            else:
                value = "&mdash;"
                sub = "Unavailable this scan"
            cells.append(
                f'<td style="padding:4px;"><div class="sc-tile">'
                f'<div class="sc-tile-name">{html.escape(name)}</div>'
                f'<div class="sc-tile-value">{value}</div>'
                f'<div class="sc-tile-sub">{sub}</div></div></td>'
            )
        tiles = (
            '<div class="sc-section-label">Seen by AI &mdash; by Platform</div>'
            f'<table style="width:100%;border-collapse:collapse;"><tr>{"".join(cells)}</tr></table>'
        )

    changed_block = (
        '<div class="sc-section-label">What Changed</div>'
        f'<div class="sc-changed">{safe_narrative}</div>'
        if safe_narrative
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><style>{_SCORECARD_CSS}</style></head>
<body>
  <div class="sc-top">
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td><span class="sc-logo">SeenBy</span></td>
        <td style="text-align:right;" class="sc-kicker">
          AI Visibility Scorecard &middot; {generated_date}
        </td>
      </tr>
    </table>
  </div>

  <p class="sc-client">{safe_name}</p>

  <table style="width:100%;border-collapse:collapse;margin-top:18px;">
    <tr>
      <td style="width:200px;vertical-align:middle;">
        <div class="sc-score-box">
          <div class="sc-score-value">{data.overall_score:.0f}</div>
          <div class="sc-score-label">GEO Score &middot; {data.score_band.title()}</div>
        </div>
      </td>
      <td style="padding-left:28px;vertical-align:middle;">
        <div class="sc-headline">{html.escape(headline)}</div>
        {benchmark_chip}
      </td>
    </tr>
  </table>

  {tiles}
  {changed_block}

  <div class="sc-foot">
    AI visibility across ChatGPT, Perplexity, Gemini and Claude.
    Tracked by SeenBy &middot; contact@seenby.my
  </div>
</body>
</html>"""


def generate_scorecard_pdf(client_id: uuid.UUID, db: Session) -> bytes | None:
    """Render the one-page scorecard to PDF bytes. Not persisted — it's an on-demand
    snapshot. Returns None when the client is archived/prospect or has no scan data."""
    client = db.get(Client, client_id)
    if not client or client.archived_at is not None:
        return None
    if client.is_prospect:
        logger.info("scorecard_skipped_prospect", client_id=str(client_id))
        return None

    data = _gather_report_data(client, db)
    if data is None:
        logger.warning("no_scan_data_for_scorecard", client_id=str(client_id))
        return None

    if weasyprint is None:
        raise RuntimeError(
            "WeasyPrint native libraries are not available — cannot render the scorecard "
            "on this host. Install the GTK/Pango runtime or render on a worker that has it."
        )

    benchmark = compute_industry_benchmark(client, db)
    scorecard_html = _build_scorecard_html(client, data, benchmark)
    return weasyprint.HTML(string=scorecard_html).write_pdf()


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
        raise RuntimeError(
            "WeasyPrint native libraries are not available — cannot render PDF reports "
            "on this host. Install the GTK/Pango runtime or generate reports on a worker "
            "that has it."
        )

    report_html = _build_report_html(client, data)
    pdf_bytes = weasyprint.HTML(string=report_html).write_pdf()

    key = f"reports/{client_id}/{utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
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

    report.sent_at = utcnow()
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
