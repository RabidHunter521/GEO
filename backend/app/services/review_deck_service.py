"""One-click 90-day review deck (landscape PDF slides).

A read-only projection over rows other services already produce: GeoScore,
ScanQueryResult, published WorkLogEntry rows, ConversionEvent (via
business_impact_service) and open ActionRecommendation rows. It adds no
tables, persists nothing and never calls an LLM — every sentence is a template
filled from a stored value, so the deck can be rebuilt at any time and always
matches the data behind it.

Two modes:
  - "client": the renewal conversation. Names the client, closes on the next
    90 days of open recommendations.
  - "case_study": the same evidence as a sales asset. The client's name, legal
    name and domain are replaced with "the client" in every free-text field,
    competitor names with "[a competitor]", and the cover describes the
    business by industry and country only. It closes on a SeenBy call to
    action instead of the client's open work.

Evidence discipline (docs/methodology.md "Evidence levels"): every headline
number carries a label for the kind of evidence behind it. Scan numbers are
Observed; delivered work is Reviewed (an admin published it); business impact
keeps its own Observed / Attributed / Assisted / Estimated ladder per currency
and is never summed across levels. A score delta is only narrated as movement
when both scores came from the same formula version
(scoring_service.scores_comparable).
"""
import html
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse

import structlog
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.core.constants import (
    COMPANY_IDENTITY_LINE,
    EVIDENCE_OBSERVED,
    EVIDENCE_REVIEWED,
    PLATFORM_LABELS,
    SCORE_DISPLAY_LABEL,
    SCORE_VERSION,
    WORK_LOG_CATEGORIES,
    WORK_LOG_CATEGORY_LABELS,
)
from app.core.time import utcnow
from app.models.action_recommendation import ActionRecommendation
from app.models.client import Client
from app.models.competitor import Competitor
from app.models.geo_score import GeoScore
from app.models.scan_query_result import ScanQueryResult
from app.services import business_impact_service, proof_card_service, work_log_service
from app.services.language_sanitizer import sanitize_text
from app.services.scoring_service import get_score_band, scores_comparable
from app.services.scoring_service import scored_results

try:
    import weasyprint  # noqa: F401 — used when generating PDF bytes
except (ImportError, OSError):
    weasyprint = None

logger = structlog.get_logger()

REVIEW_DECK_WINDOW_DAYS = 90
REVIEW_DECK_MODES = ("client", "case_study")

_MAX_WINS = 4
_MAX_WORK_ITEMS = 8
_MAX_NEXT_ACTIONS = 3
_ANON_CLIENT = "the client"
_ANON_COMPETITOR = "[a competitor]"

# Client-facing dimension names — same vocabulary as the public client view
# (client_period_summary_service._DIMENSION_LABELS): "AI Presence", never the
# admin-only "AI Citability".
_DIMENSION_LABELS: dict[str, str] = {
    "ai_citability": "AI Presence",
    "brand_authority": "Brand Authority",
    "content_quality": "Content Quality",
    "technical_foundations": "Technical Foundations",
    "structured_data": "Structured Data",
}

_EVIDENCE_LADDER = (
    ("observed", "Observed", "Directly measured"),
    ("attributed", "Attributed", "Rule-based attribution"),
    ("assisted", "Assisted", "AI-assisted matching"),
    ("estimated", "Estimated", "Modeled projection"),
)

_COLOR_HEX = {"green": "#059669", "yellow": "#d97706", "red": "#dc2626"}


@dataclass
class DeckWin:
    query_text: str
    platform_label: str
    excerpt: str | None


@dataclass
class DeckPlatformRow:
    label: str
    then: float | None
    now: float | None


@dataclass
class DeckImpact:
    currency: str
    values_minor: dict[str, int]
    counts: dict[str, int]
    caveats: list[str]


@dataclass
class ReviewDeckData:
    mode: str
    display_name: str
    descriptor: str
    window_start: datetime
    window_end: datetime
    since_onboarding: bool
    score_now: float
    score_then: float | None
    presence_now: float
    presence_then: float | None
    comparable: bool
    seen_now: int
    total_now: int
    seen_then: int | None
    total_then: int | None
    platforms: list[DeckPlatformRow] = field(default_factory=list)
    wins: list[DeckWin] = field(default_factory=list)
    newly_seen_total: int = 0
    work_counts: dict[str, int] = field(default_factory=dict)
    work_items: list[tuple[str, str, str]] = field(default_factory=list)  # (date, category, text)
    work_total: int = 0
    impacts: list[DeckImpact] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


# --- anonymisation ----------------------------------------------------------

def _domain_of(website: str | None) -> str | None:
    if not website:
        return None
    parsed = urlparse(website if "//" in website else f"//{website}")
    host = (parsed.hostname or "").lower()
    return host.removeprefix("www.") or None


def build_redactor(client: Client, competitor_names: list[str], anonymize: bool):
    """Return a str -> str function applied to every free-text field.

    Always applies the §2 vocabulary sanitizer. In case-study mode it also
    swaps the client's identity for "the client" and each competitor for
    "[a competitor]". Longest names go first so "Acme Dental Group" is not
    left as "the client Group" by an earlier "Acme Dental" pass.
    """
    identity = (client.name, getattr(client, "legal_name", None), _domain_of(client.website))
    client_terms = [t.strip() for t in identity if t and t.strip()] if anonymize else []
    rival_terms = [n.strip() for n in competitor_names if n and n.strip()] if anonymize else []

    patterns = [
        (re.compile(rf"(?<!\w){re.escape(t)}(?!\w)", re.IGNORECASE), _ANON_CLIENT)
        for t in sorted(set(client_terms), key=len, reverse=True)
    ] + [
        (re.compile(rf"(?<!\w){re.escape(t)}(?!\w)", re.IGNORECASE), _ANON_COMPETITOR)
        for t in sorted(set(rival_terms), key=len, reverse=True)
    ]

    def redact(text: str | None) -> str:
        out = sanitize_text(text or "")
        for pattern, repl in patterns:
            out = pattern.sub(repl, out)
        return out

    return redact


def _descriptor(client: Client) -> str:
    industry = (client.industry or "").strip() or "local"
    country = (client.country or "").strip()
    article = "An" if industry[:1].lower() in "aeiou" else "A"
    where = f" in {country}" if country else ""
    return f"{article} {industry} business{where}"


# --- data gathering ---------------------------------------------------------

def _own_results(scan_id: uuid.UUID, db: Session) -> list[ScanQueryResult]:
    return (
        db.query(ScanQueryResult)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
        )
        .all()
    )


def _visibility(entry: dict | None) -> float | None:
    if not entry or entry.get("status") != "ok":
        return None
    return float(entry.get("visibility", 0.0))


def _pick_scores(client_id: uuid.UUID, start: datetime, db: Session):
    """(baseline, current) GeoScore rows for the window.

    Baseline is the last score on or before the window start — the state the
    client was in when the 90 days began. A client younger than the window has
    none, so the earliest score inside the window stands in. Ties break on id
    so two calls can never pick different rows.
    """
    current = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
        .first()
    )
    if current is None:
        return None, None
    baseline = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id, GeoScore.computed_at <= start)
        .order_by(desc(GeoScore.computed_at), desc(GeoScore.id))
        .first()
    ) or (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client_id, GeoScore.computed_at > start)
        .order_by(asc(GeoScore.computed_at), asc(GeoScore.id))
        .first()
    )
    if baseline is not None and baseline.id == current.id:
        baseline = None
    return baseline, current


def gather_review_deck_data(client: Client, db: Session, mode: str = "client") -> ReviewDeckData | None:
    if mode not in REVIEW_DECK_MODES:
        raise ValueError(f"unknown review deck mode: {mode}")
    anonymize = mode == "case_study"

    end = utcnow()
    start = end - timedelta(days=REVIEW_DECK_WINDOW_DAYS)
    since_onboarding = False
    if client.created_at and client.created_at > start:
        start = client.created_at
        since_onboarding = True

    baseline, current = _pick_scores(client.id, start, db)
    if current is None:
        return None

    competitor_names = [
        c.name for c in db.query(Competitor).filter(Competitor.client_id == client.id).all()
    ]
    redact = build_redactor(client, competitor_names, anonymize)

    comparable = baseline is not None and scores_comparable(
        current.score_version, baseline.score_version
    )

    latest_results = _own_results(current.scan_id, db)
    base_results = _own_results(baseline.scan_id, db) if baseline else []

    data = ReviewDeckData(
        mode=mode,
        display_name=_ANON_CLIENT.capitalize() if anonymize else client.name,
        descriptor=_descriptor(client),
        window_start=start,
        window_end=end,
        since_onboarding=since_onboarding,
        score_now=current.overall_score,
        score_then=baseline.overall_score if baseline else None,
        presence_now=current.ai_citability,
        presence_then=baseline.ai_citability if baseline else None,
        comparable=comparable,
        seen_now=sum(1 for r in scored_results(latest_results) if r.brand_detected),
        total_now=len(scored_results(latest_results)),
        seen_then=(
            sum(1 for r in scored_results(base_results) if r.brand_detected) if baseline else None
        ),
        total_then=len(scored_results(base_results)) if baseline else None,
    )

    # Per platform, then vs now. A platform unavailable on either scan shows a
    # dash rather than a zero — a zero would read as "not seen".
    now_bd = current.platform_breakdown or {}
    then_bd = (baseline.platform_breakdown or {}) if baseline else {}
    for code in PLATFORM_LABELS:
        if code not in now_bd and code not in then_bd:
            continue
        data.platforms.append(DeckPlatformRow(
            label=PLATFORM_LABELS[code],
            then=_visibility(then_bd.get(code)),
            now=_visibility(now_bd.get(code)),
        ))

    # Wins: questions Not seen by AI at the baseline scan and Seen by AI now,
    # matched on (platform, category, question). Hallucination-flagged rows are
    # excluded — their brand_detected flag is unreliable (scan_diff_service).
    if baseline:
        was_seen = {
            (r.platform, r.category, r.query_text): r.brand_detected for r in base_results
        }
        flips = [
            r for r in latest_results
            if r.brand_detected
            and not r.hallucination_flagged
            and was_seen.get((r.platform, r.category, r.query_text)) is False
        ]
        flips.sort(key=proof_card_service._sort_key)
        data.newly_seen_total = len(flips)
        for r in flips[:_MAX_WINS]:
            _, excerpt = proof_card_service.result_excerpt(
                r, client.name, competitor_names, redact=True
            )
            data.wins.append(DeckWin(
                query_text=redact(r.query_text),
                platform_label=PLATFORM_LABELS.get(r.platform, r.platform.title()),
                excerpt=redact(excerpt) if excerpt else None,
            ))

    # Delivered work: published rows only (work_log_service filters status at
    # the query), scoped the same way the monthly report scopes them.
    try:
        entries = work_log_service.published_entries(client.id, db, since=start.date())
    except Exception:
        db.rollback()
        logger.warning("review_deck_work_log_failed", client_id=str(client.id))
        entries = []
    data.work_total = len(entries)
    counts = {c: 0 for c in WORK_LOG_CATEGORIES}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1
    data.work_counts = {k: v for k, v in counts.items() if v}
    data.work_items = [
        (e.entry_date.strftime("%d %b"), work_log_service.category_label(e), redact(e.description))
        for e in entries[:_MAX_WORK_ITEMS]
    ]

    try:
        summaries = business_impact_service.get_impact_summary(
            client.id, db, date_from=start.date(), date_to=end.date()
        )
    except Exception:
        db.rollback()
        logger.warning("review_deck_impact_failed", client_id=str(client.id))
        summaries = []
    for s in summaries:
        data.impacts.append(DeckImpact(
            currency=s.currency,
            values_minor={key: getattr(s, f"{key}_value_minor", 0) for key, _, _ in _EVIDENCE_LADDER},
            counts=dict(s.event_count_by_level),
            caveats=list(s.caveats),
        ))

    if not anonymize:
        rows = (
            db.query(ActionRecommendation)
            .filter(
                ActionRecommendation.client_id == client.id,
                ActionRecommendation.status == "open",
            )
            .order_by(desc(ActionRecommendation.estimated_impact), desc(ActionRecommendation.generated_at))
            .limit(_MAX_NEXT_ACTIONS)
            .all()
        )
        for a in rows:
            label = _DIMENSION_LABELS.get(a.dimension, a.dimension.replace("_", " ").title())
            data.next_actions.append(f"{label}: {redact(a.action_text)}")

    return data


# --- rendering --------------------------------------------------------------

_CSS = """
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Inter', -apple-system, 'Helvetica Neue', Arial, sans-serif;
       color: #0f172a; font-size: 12pt; }
.slide { width: 297mm; height: 210mm; padding: 18mm 22mm 20mm; position: relative;
         page-break-after: always; overflow: hidden; }
.slide:last-child { page-break-after: auto; }
.dark { background: #070d1a; color: #ffffff; }
.kicker { font-size: 9.5pt; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; }
.dark .kicker { color: #94a3b8; }
h1 { font-size: 34pt; margin: 6mm 0 3mm; line-height: 1.1; }
h2 { font-size: 22pt; margin: 2mm 0 8mm; line-height: 1.2; }
.sub { font-size: 13pt; color: #475569; }
.dark .sub { color: #cbd5e1; }
.foot { position: absolute; left: 22mm; right: 22mm; bottom: 9mm; font-size: 8pt; color: #94a3b8;
        border-top: 1px solid #e2e8f0; padding-top: 2mm; }
.dark .foot { border-top-color: #1e293b; }
.chip { display: inline-block; font-size: 8pt; font-weight: 600; padding: 1mm 2.5mm;
        border-radius: 3mm; background: #e0f2fe; color: #075985; vertical-align: middle; }
.chip.reviewed { background: #ede9fe; color: #5b21b6; }
.chip.attributed { background: #fef3c7; color: #92400e; }
.chip.assisted { background: #f1f5f9; color: #334155; }
.chip.estimated { background: #f1f5f9; color: #64748b; font-style: italic; }
table.grid { width: 100%; border-collapse: collapse; }
table.grid td { vertical-align: top; padding: 0 4mm 0 0; }
.stat { border: 1px solid #e2e8f0; border-radius: 4mm; padding: 6mm; }
.stat-label { font-size: 9.5pt; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { font-size: 40pt; font-weight: 700; margin: 2mm 0; }
.stat-then { font-size: 11pt; color: #64748b; }
.note { font-size: 9.5pt; color: #64748b; margin-top: 6mm; }
table.rows { width: 100%; border-collapse: collapse; font-size: 11pt; }
table.rows th { text-align: left; font-size: 9pt; color: #64748b; text-transform: uppercase;
                border-bottom: 1px solid #e2e8f0; padding: 2mm 0; }
table.rows td { border-bottom: 1px solid #f1f5f9; padding: 2.5mm 0; vertical-align: top; }
.num, table.rows th.num { text-align: right; }
.quote { border-left: 3px solid #059669; padding: 1mm 0 1mm 4mm; margin: 0 0 5mm; }
.quote-q { font-size: 10pt; color: #64748b; }
.quote-a { font-size: 12pt; margin-top: 1mm; }
.logo { font-weight: 700; font-size: 14pt; }
.cta { font-size: 16pt; margin-top: 10mm; }
"""


def _esc(text) -> str:
    return html.escape(str(text))


def _chip(label: str, kind: str = "") -> str:
    return f'<span class="chip {kind}">{_esc(label)}</span>'


def _fmt_date(d: datetime) -> str:
    return d.strftime("%d %b %Y")


def _foot(data: ReviewDeckData) -> str:
    who = "Client identity withheld" if data.mode == "case_study" else _esc(data.display_name)
    return (
        f'<div class="foot">SeenBy &middot; {who} &middot; '
        f'{_fmt_date(data.window_start)} &ndash; {_fmt_date(data.window_end)} &middot; '
        f'{_esc(COMPANY_IDENTITY_LINE)}</div>'
    )


def _score_hex(score: float) -> str:
    _, color = get_score_band(score)
    return _COLOR_HEX.get(color, "#0f172a")


def _cover_slide(data: ReviewDeckData) -> str:
    if data.mode == "case_study":
        kicker = "Case study &middot; 90 days of AI visibility work"
        title = _esc(data.descriptor)
    else:
        kicker = "90-day review"
        title = _esc(data.display_name)
    days = (data.window_end - data.window_start).days
    span = f"Since onboarding ({days} days)" if data.since_onboarding else "The last 90 days"
    return f"""
<section class="slide dark">
  <div class="logo">SeenBy</div>
  <div style="margin-top:38mm;">
    <div class="kicker">{kicker}</div>
    <h1>{title}</h1>
    <div class="sub">{span}: {_fmt_date(data.window_start)} &ndash; {_fmt_date(data.window_end)}</div>
    <div class="sub" style="margin-top:3mm;">How often ChatGPT, Perplexity, Gemini and Claude recommend this business, and the work behind it.</div>
  </div>
  {_foot(data)}
</section>"""


def _then_line(then: float | None, comparable: bool, suffix: str = "") -> str:
    if then is None:
        return "No earlier score in this window to compare against"
    if not comparable:
        return f"Was {then:.0f}{suffix} under an earlier version of the method"
    return f"Was {then:.0f}{suffix} at the start"


def _headline(data: ReviewDeckData) -> str:
    if data.score_then is None:
        return f"{SCORE_DISPLAY_LABEL} is {data.score_now:.0f} today"
    if not data.comparable:
        return (
            f"{SCORE_DISPLAY_LABEL} is {data.score_now:.0f} today. The scoring method was "
            "updated during this period, so the two numbers are not directly comparable"
        )
    delta = data.score_now - data.score_then
    if delta >= 0.5:
        return f"{SCORE_DISPLAY_LABEL} rose from {data.score_then:.0f} to {data.score_now:.0f}"
    if delta <= -0.5:
        return f"{SCORE_DISPLAY_LABEL} moved from {data.score_then:.0f} to {data.score_now:.0f}"
    return f"{SCORE_DISPLAY_LABEL} held at {data.score_now:.0f}"


def _results_slide(data: ReviewDeckData) -> str:
    seen_then = (
        f"Was {data.seen_then} of {data.total_then} at the start"
        if data.seen_then is not None and data.total_then
        else "No earlier scan in this window to compare against"
    )
    method_note = (
        f'<div class="note">Scores use the {SCORE_VERSION} method. Where the method changed between '
        "the two scores, part of the difference comes from the method, not from the market.</div>"
        if data.score_then is not None and not data.comparable else ""
    )
    return f"""
<section class="slide">
  <div class="kicker">The result {_chip(EVIDENCE_OBSERVED)}</div>
  <h2>{_esc(_headline(data))}</h2>
  <table class="grid"><tr>
    <td style="width:33%;"><div class="stat">
      <div class="stat-label">{SCORE_DISPLAY_LABEL}</div>
      <div class="stat-value" style="color:{_score_hex(data.score_now)};">{data.score_now:.0f}</div>
      <div class="stat-then">{_esc(_then_line(data.score_then, data.comparable))}</div>
    </div></td>
    <td style="width:33%;"><div class="stat">
      <div class="stat-label">AI Presence</div>
      <div class="stat-value">{data.presence_now:.0f}%</div>
      <div class="stat-then">{_esc(_then_line(data.presence_then, data.comparable, "%"))}</div>
    </div></td>
    <td style="width:34%;"><div class="stat">
      <div class="stat-label">Buyer questions Seen by AI</div>
      <div class="stat-value">{data.seen_now}<span style="font-size:20pt;color:#64748b;"> / {data.total_now}</span></div>
      <div class="stat-then">{_esc(seen_then)}</div>
    </div></td>
  </tr></table>
  <div class="note">Observed: counted from the AI answers SeenBy recorded on each scan.</div>
  {method_note}
  {_foot(data)}
</section>"""


def _platform_slide(data: ReviewDeckData) -> str:
    if not data.platforms:
        return ""

    def cell(v: float | None) -> str:
        return "&mdash;" if v is None else f"{v:.0f}%"

    rows = "".join(
        f"<tr><td>{_esc(p.label)}</td><td class='num'>{cell(p.then)}</td>"
        f"<td class='num'><strong>{cell(p.now)}</strong></td></tr>"
        for p in data.platforms
    )
    return f"""
<section class="slide">
  <div class="kicker">By AI platform {_chip(EVIDENCE_OBSERVED)}</div>
  <h2>How often each AI platform shows this business</h2>
  <table class="rows">
    <thead><tr><th>Platform</th><th class="num">Start of period</th><th class="num">Now</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="note">Share of tracked buyer questions where the business was Seen by AI.
  A dash means the platform was unavailable on that scan.</div>
  {_foot(data)}
</section>"""


def _wins_slide(data: ReviewDeckData) -> str:
    if not data.wins:
        return ""
    quotes = ""
    for w in data.wins:
        answer = f'<div class="quote-a">&ldquo;{_esc(w.excerpt)}&rdquo;</div>' if w.excerpt else ""
        quotes += (
            f'<div class="quote"><div class="quote-q">{_esc(w.platform_label)} &middot; '
            f'&ldquo;{_esc(w.query_text)}&rdquo;</div>{answer}</div>'
        )
    more = data.newly_seen_total - len(data.wins)
    more_line = f'<div class="note">Plus {more} more questions now Seen by AI.</div>' if more > 0 else ""
    n = data.newly_seen_total
    return f"""
<section class="slide">
  <div class="kicker">Proof {_chip(EVIDENCE_OBSERVED)}</div>
  <h2>{n} buyer question{"" if n == 1 else "s"} went from Not seen by AI to Seen by AI</h2>
  {quotes}
  {more_line}
  {_foot(data)}
</section>"""


def _work_slide(data: ReviewDeckData) -> str:
    if not data.work_total:
        return ""
    tiles = "".join(
        f'<td><div class="stat" style="padding:4mm;"><div class="stat-label">'
        f'{_esc(WORK_LOG_CATEGORY_LABELS.get(cat, cat.title()))}</div>'
        f'<div class="stat-value" style="font-size:26pt;">{n}</div></div></td>'
        for cat, n in data.work_counts.items()
    )
    rows = "".join(
        f"<tr><td style='width:16%;'>{_esc(d)}</td><td style='width:16%;'>{_esc(c)}</td>"
        f"<td>{_esc(t)}</td></tr>"
        for d, c, t in data.work_items
    )
    more = data.work_total - len(data.work_items)
    more_line = f'<div class="note">Plus {more} more items in the full work log.</div>' if more > 0 else ""
    n = data.work_total
    return f"""
<section class="slide">
  <div class="kicker">What SeenBy delivered {_chip(EVIDENCE_REVIEWED, "reviewed")}</div>
  <h2>{n} improvement{"" if n == 1 else "s"} delivered</h2>
  <table class="grid" style="margin-bottom:6mm;"><tr>{tiles}</tr></table>
  <table class="rows">
    <thead><tr><th>Date</th><th>Area</th><th>Work</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {more_line}
  {_foot(data)}
</section>"""


def _impact_slide(data: ReviewDeckData) -> str:
    if not data.impacts:
        return ""
    blocks = ""
    for imp in data.impacts:
        rows = ""
        for key, label, desc_ in _EVIDENCE_LADDER:
            value = imp.values_minor.get(key, 0) / 100
            count = imp.counts.get(key, 0)
            style = ' style="color:#64748b;font-style:italic;"' if key == "estimated" else ""
            rows += (
                f"<tr{style}><td>{_chip(label, key if key != 'observed' else '')} "
                f"{_esc(desc_)}</td><td class='num'>{_esc(imp.currency)} {value:,.2f}</td>"
                f"<td class='num'>{count}</td></tr>"
            )
        caveats = "<br>".join(_esc(c) for c in imp.caveats)
        blocks += f"""
  <table class="rows" style="margin-bottom:4mm;">
    <thead><tr><th>Evidence level ({_esc(imp.currency)})</th><th class="num">Value</th><th class="num">Events</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div class="note" style="margin-top:0;margin-bottom:6mm;">{caveats}</div>"""
    return f"""
<section class="slide">
  <div class="kicker">Business impact</div>
  <h2>Enquiries and sales associated with AI visibility</h2>
  {blocks}
  {_foot(data)}
</section>"""


def _closing_slide(data: ReviewDeckData) -> str:
    if data.mode == "case_study":
        return f"""
<section class="slide dark">
  <div class="logo">SeenBy</div>
  <div style="margin-top:40mm;">
    <div class="kicker">Want results like these?</div>
    <h1>Get your business recommended by AI</h1>
    <div class="cta">contact@seenby.my</div>
    <div class="sub" style="margin-top:6mm;">Every number in this case study comes from SeenBy's own scan records and
    delivery log. Client identity withheld.</div>
  </div>
  {_foot(data)}
</section>"""
    items = (
        "".join(f"<tr><td>{_esc(a)}</td></tr>" for a in data.next_actions)
        if data.next_actions
        else "<tr><td>We will agree the next priorities together in the review call.</td></tr>"
    )
    return f"""
<section class="slide">
  <div class="kicker">The next 90 days</div>
  <h2>Where we focus next</h2>
  <table class="rows"><tbody>{items}</tbody></table>
  <div class="note">Questions about this review: contact@seenby.my</div>
  {_foot(data)}
</section>"""


def build_review_deck_html(data: ReviewDeckData) -> str:
    slides = "".join([
        _cover_slide(data),
        _results_slide(data),
        _platform_slide(data),
        _wins_slide(data),
        _work_slide(data),
        _impact_slide(data),
        _closing_slide(data),
    ])
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        f"<style>{_CSS}</style></head><body>{slides}</body></html>"
    )


def generate_review_deck_pdf(client_id: uuid.UUID, db: Session, mode: str = "client") -> bytes | None:
    """Render the deck to PDF bytes. Not persisted — rebuilt on each click.

    Returns None for an archived client, a prospect (no retainer to review)
    or a client with no score yet.
    """
    client = db.get(Client, client_id)
    if not client or client.archived_at is not None:
        return None
    if client.is_prospect:
        logger.info("review_deck_skipped_prospect", client_id=str(client_id))
        return None

    data = gather_review_deck_data(client, db, mode)
    if data is None:
        logger.warning("no_scan_data_for_review_deck", client_id=str(client_id))
        return None

    if weasyprint is None:
        raise RuntimeError(
            "WeasyPrint native libraries are not available — cannot render the review deck "
            "on this host. Install the GTK/Pango runtime or render on a worker that has it."
        )

    logger.info("review_deck_generated", client_id=str(client_id), mode=mode)
    return weasyprint.HTML(string=build_review_deck_html(data)).write_pdf()
