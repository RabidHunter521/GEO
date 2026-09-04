"""Derives client-facing GEO issues from scan results and dimension scores.

All issue text here is client-facing: it must follow the language rules in
CLAUDE.md (no "cited", "citation rate", "mentioned" — use "Seen by AI" /
"visibility frequency"). Issues state the problem only, never the fix —
remediation comes from the SeenBy team.

Governing rule (CLAUDE.md §2 / seenby-client-output rule 2): a group may only
be emitted when we actually observed something. The reviewed dimensions
(brand_authority, content_quality) are gated on an admin-accepted assessment,
because their score defaults to 0 on the Client model — an unassessed client
scores 0 for "nobody has looked yet", and reading that as "scored badly" told
clients specific things about their business ("Sparse customer reviews or
testimonials") that we had never researched, under a badge claiming public
evidence and human review. The auto-verified dimensions report only the fact
the verification crawler actually establishes.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.constants import DIMENSION_EVIDENCE_LABEL, SCORE_BANDS
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult

_GOOD = SCORE_BANDS["good"][0]        # 65
_FAIR = SCORE_BANDS["fair"][0]        # 50
_DEVELOPING = SCORE_BANDS["developing"][0]  # 35

# Category-specific findings when the brand was not seen in any query of
# that category in the latest scan.
_CATEGORY_ISSUES = {
    "brand": "Not seen by AI when people ask directly about your brand",
    "comparison": "Not seen by AI in comparison questions against competitors",
    "recommendation": "Not seen by AI in 'best in your industry' recommendation questions",
    "local": "Not seen by AI in local search questions for your area",
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

# Auto-verified dimensions report ONLY what the verification crawler actually
# establishes. The previous tail of this list ("Crawlability and indexing
# problems", "Missing or incomplete meta information", "Page speed and mobile
# experience need improvement") was emitted from the score alone — we never
# measure crawl health, meta tags or page speed anywhere, so those were claims
# about the client's site that no stored observation supported. Deleted rather
# than left unused, so they cannot be re-wired by accident. If we ever want
# them back, source them from site_audit_service, which does measure.
_TECHNICAL_ISSUES = [
    "Website is not yet verified as accessible to AI crawlers",
]

# Both lines restate the one fact structured_data_verified records. The former
# tail ("Missing organization and business schema", "Missing FAQ or article
# schema") named specific schema types we never look for individually.
_STRUCTURED_DATA_ISSUES = [
    "No verified schema markup implemented",
    "Key business information is not yet machine-readable",
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


def _is_reviewed(client_id, dimension: str, db: Session) -> bool:
    """True only when an admin has accepted (or adjusted) an assessment for this
    dimension. Mirrors client_view._accepted_bullets — a Claude suggestion that
    nobody signed off on is not a review, so "suggested" does not count.

    This is what makes DIMENSION_EVIDENCE_LABEL truthful: the badge is attached
    to a group only where the review it claims actually happened.
    """
    return (
        db.query(DimensionAssessment.id)
        .filter(
            DimensionAssessment.client_id == client_id,
            DimensionAssessment.dimension == dimension,
            DimensionAssessment.status.in_(("accepted", "adjusted")),
        )
        .first()
        is not None
    )


def _group(dimension: str, label: str, issues: list[str], *, reviewed: bool = False) -> dict:
    """One issue group. `evidence_label` is set only for reviewed dimensions, so
    the client view renders the badge from the data instead of asserting it."""
    return {
        "dimension": dimension,
        "dimension_label": label,
        "issues": issues,
        "evidence_label": DIMENSION_EVIDENCE_LABEL if reviewed else None,
    }


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
                ScanQueryResult.is_control.is_(False),
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
        groups.append(_group("ai_visibility", "AI Visibility", ai_issues))

    # ── Reviewed dimensions — only once a human has signed off ───────────────
    # Gated on an accepted assessment, not on the score: brand_authority_score
    # and content_quality_score default to 0, so an unassessed client would
    # otherwise be shown the full pool of findings nobody researched.
    if _is_reviewed(client.id, "brand_authority", db):
        ba_issues = _tiered(_BRAND_AUTHORITY_ISSUES, latest_score.brand_authority)
        if ba_issues:
            groups.append(
                _group("brand_authority", "Brand Authority", ba_issues, reviewed=True)
            )

    if _is_reviewed(client.id, "content_quality", db):
        cq_issues = _tiered(_CONTENT_QUALITY_ISSUES, latest_score.content_quality)
        if cq_issues:
            groups.append(
                _group("content_quality", "Content Quality", cq_issues, reviewed=True)
            )

    # ── Toolkit-verified dimensions ──────────────────────────────────────────
    # Each reports exactly one verified fact. The score check the technical
    # branch used to carry was redundant (the dimension is 0 or 100, so
    # "< good" and "not verified" are the same condition) and it was what let
    # the unmeasured claims through.
    if not client.technical_foundations_verified:
        groups.append(
            _group("technical_foundations", "Technical Foundations", list(_TECHNICAL_ISSUES))
        )

    if not client.structured_data_verified:
        groups.append(
            _group("structured_data", "Structured Data", list(_STRUCTURED_DATA_ISSUES))
        )

    return groups
