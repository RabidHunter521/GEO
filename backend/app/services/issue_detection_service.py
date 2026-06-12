"""Derives client-facing GEO issues from scan results and dimension scores.

All issue text here is client-facing: it must follow the language rules in
CLAUDE.md (no "cited", "citation rate", "mentioned" — use "Seen by AI" /
"visibility frequency"). Issues state the problem only, never the fix —
remediation comes from the SeenBy team.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.constants import SCORE_BANDS
from app.models.client import Client
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult

_GOOD = SCORE_BANDS["good"][0]        # 65
_FAIR = SCORE_BANDS["fair"][0]        # 50
_DEVELOPING = SCORE_BANDS["developing"][0]  # 35

# Category-specific findings when the brand was not seen in any query of
# that category in the latest scan.
_CATEGORY_ISSUES = {
    "brand": "Not yet seen by AI when people ask directly about your brand",
    "comparison": "Not yet seen by AI in comparison questions against competitors",
    "recommendation": "Not yet seen by AI in 'best in your industry' recommendation questions",
    "local": "Not yet seen by AI in local search questions for your area",
}

# Generic issue pools per manually assessed dimension. Lower scores surface
# more of the list (ordered most fundamental first).
_BRAND_AUTHORITY_ISSUES = [
    "Limited presence across trusted and authoritative websites",
    "Few backlinks from authoritative sources",
    "Low online reputation and trust signals",
    "Weak industry recognition and third-party validation",
    "Minimal media coverage",
    "Sparse customer reviews or testimonials",
]

_CONTENT_QUALITY_ISSUES = [
    "Content does not yet answer user questions effectively",
    "Thin or shallow content in key areas",
    "Limited topical coverage",
    "Weak expertise, authority, and trust indicators",
    "Content structure and readability need improvement",
    "Missing supporting evidence, examples, or data",
]

_TECHNICAL_ISSUES = [
    "Website is not yet verified as accessible to AI crawlers",
    "Crawlability and indexing problems",
    "Missing or incomplete meta information",
    "Page speed and mobile experience need improvement",
]

_STRUCTURED_DATA_ISSUES = [
    "No verified schema markup implemented",
    "Key business information is not yet machine-readable",
    "Missing organization and business schema",
    "Missing FAQ or article schema",
]


def _tiered(pool: list[str], score: float) -> list[str]:
    """Surface more of the pool the lower the score. Nothing at good+."""
    if score >= _GOOD:
        return []
    if score >= _FAIR:
        return pool[:2]
    if score >= _DEVELOPING:
        return pool[:4]
    return pool


def detect_client_issues(client: Client, db: Session) -> list[dict]:
    """Issue groups per dimension for the read-only client view.

    Returns [] when no score has been computed yet (nothing to report on).
    """
    latest_score = (
        db.query(GeoScore)
        .filter(GeoScore.client_id == client.id)
        .order_by(GeoScore.computed_at.desc())
        .first()
    )
    if not latest_score:
        return []

    groups: list[dict] = []

    # ── AI Visibility — derived from the latest completed scan ──────────────
    ai_issues: list[str] = []
    latest_scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )
    if latest_scan:
        results = (
            db.query(ScanQueryResult)
            .filter(
                ScanQueryResult.scan_id == latest_scan.id,
                ScanQueryResult.hallucination_flagged.is_(False),
            )
            .all()
        )
        client_results = [r for r in results if r.competitor_id is None]

        seen_count = sum(1 for r in client_results if r.brand_detected)
        if client_results:
            frequency = seen_count / len(client_results) * 100
            if frequency < _FAIR:
                ai_issues.append("Your brand rarely appears in AI-generated answers")
            elif frequency < _GOOD:
                ai_issues.append("Low visibility frequency across AI platforms")

        for category, issue in _CATEGORY_ISSUES.items():
            cat_results = [r for r in client_results if r.category == category]
            if cat_results and not any(r.brand_detected for r in cat_results):
                ai_issues.append(issue)

        # Any competitor seen more often than the client in the same scan.
        comp_seen: dict[uuid.UUID, list[bool]] = {}
        for r in results:
            if r.competitor_id is not None:
                comp_seen.setdefault(r.competitor_id, []).append(r.brand_detected)
        client_freq = (
            seen_count / len(client_results) if client_results else 0.0
        )
        if any(
            sum(flags) / len(flags) > client_freq
            for flags in comp_seen.values()
            if flags
        ):
            ai_issues.append("Competitors are seen by AI more frequently than your brand")

    if ai_issues:
        groups.append({
            "dimension": "ai_visibility",
            "dimension_label": "AI Visibility",
            "issues": ai_issues,
        })

    # ── Manually assessed dimensions — tiered generic findings ──────────────
    ba_issues = _tiered(_BRAND_AUTHORITY_ISSUES, latest_score.brand_authority)
    if ba_issues:
        groups.append({
            "dimension": "brand_authority",
            "dimension_label": "Brand Authority",
            "issues": ba_issues,
        })

    cq_issues = _tiered(_CONTENT_QUALITY_ISSUES, latest_score.content_quality)
    if cq_issues:
        groups.append({
            "dimension": "content_quality",
            "dimension_label": "Content Quality",
            "issues": cq_issues,
        })

    # ── Toolkit-verified dimensions ──────────────────────────────────────────
    tech_issues: list[str] = []
    if not client.technical_foundations_verified:
        tech_issues.append(_TECHNICAL_ISSUES[0])
    if latest_score.technical_foundations < _GOOD:
        tech_issues.extend(_TECHNICAL_ISSUES[1:3])
    if tech_issues:
        groups.append({
            "dimension": "technical_foundations",
            "dimension_label": "Technical Foundations",
            "issues": tech_issues,
        })

    sd_issues: list[str] = []
    if not client.structured_data_verified:
        sd_issues.extend(_STRUCTURED_DATA_ISSUES[:2])
    elif latest_score.structured_data < _GOOD:
        sd_issues.extend(_STRUCTURED_DATA_ISSUES[2:4])
    if sd_issues:
        groups.append({
            "dimension": "structured_data",
            "dimension_label": "Structured Data",
            "issues": sd_issues,
        })

    return groups
