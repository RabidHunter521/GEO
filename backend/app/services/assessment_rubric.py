"""Measured criteria of the Brand Authority / Content Quality points checklist.

ASSESSMENT_RUBRICS (constants) defines the criteria. This module computes every
criterion whose basis is "measured" or "recorded" from data SeenBy already
holds; the one "judged" criterion per dimension comes from the Claude review in
assessment_service. Pure reads, no model calls, so the same data always gives
the same points.

Each criterion returns:
  points      the suggested points (0..max)
  evidence    a client-safe sentence, or None when there is nothing to show
  admin_hint  what staff can do to measure or improve it (admin-only), or None

A criterion with no data scores 0 rather than being guessed: the admin hint
says what to run, and the admin may still award points with a reason.
"""
from __future__ import annotations

import math

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.constants import ASSESSMENT_RUBRICS, DEFAULT_CORE_AUTHORITY_ASSETS
from app.models.client import Client

# ai_source_presence: share of the third-party sites AI answers drew on that
# name the business. 40% or more earns full points.
_FULL_SOURCE_SHARE_PCT = 40.0
# reviews: volume earns up to 10 points on a log scale (200 reviews = full),
# rating up to 5.
_FULL_REVIEW_COUNT = 200
_RATING_POINTS = ((4.5, 5), (4.0, 3), (3.5, 1))
# content_depth: words per crawled page that count as substantial / some depth.
_DEEP_WORDS_PER_PAGE = 500
_SOME_WORDS_PER_PAGE = 250
# page_readability: audits considered (most recent page per URL).
_MAX_AUDITED_PAGES = 10


def criteria(dimension: str) -> tuple[dict, ...]:
    return ASSESSMENT_RUBRICS[dimension]


def judged_criterion(dimension: str) -> dict:
    return next(c for c in ASSESSMENT_RUBRICS[dimension] if c["basis"] == "judged")


def measure(client: Client, dimension: str, db: Session) -> list[dict]:
    """Every non-judged criterion of `dimension`, in rubric order."""
    out = []
    for criterion in ASSESSMENT_RUBRICS[dimension]:
        if criterion["basis"] == "judged":
            continue
        points, evidence, hint = _MEASURES[criterion["key"]](client, db, criterion["max"])
        out.append({
            "key": criterion["key"],
            "label": criterion["label"],
            "max": criterion["max"],
            "basis": criterion["basis"],
            "points": max(0, min(criterion["max"], int(round(points)))),
            "evidence": evidence,
            "admin_hint": hint,
        })
    return out


# ── Brand Authority ──────────────────────────────────────────────────────────

def _directory_presence(client: Client, db: Session, max_points: int):
    from app.industry_packs import registry as pack_registry
    from app.services import authority_service

    pack = pack_registry.find_pack(getattr(client, "industry_pack", None))
    core = tuple(pack.priority_asset_keys) if pack and pack.priority_asset_keys else DEFAULT_CORE_AUTHORITY_ASSETS
    assets = {a.asset_key: a for a in authority_service.list_assets(client.id, db) if a.asset_key}
    verified = [assets[k].name for k in core if k in assets and assets[k].status == "verified"]
    live = [assets[k].name for k in core if k in assets and assets[k].status == "live"]
    points = max_points * (len(verified) + 0.5 * len(live)) / len(core)
    missing = len(core) - len(verified) - len(live)
    if not verified and not live:
        return 0, None, (
            f"None of the {len(core)} key listings is live yet. Add them on the "
            "Authority page and verify them."
        )
    parts = [f"{len(verified)} of {len(core)} key listings verified"]
    if verified:
        parts[0] += f" ({', '.join(verified)})"
    if live:
        parts.append(f"{len(live)} live but not yet verified")
    hint = (
        f"{missing} key listing{'s' if missing != 1 else ''} not set up; "
        "verifying a live listing earns the other half of its points."
        if missing or live else None
    )
    return points, "; ".join(parts) + ".", hint


def _ai_source_presence(client: Client, db: Session, max_points: int):
    from app.models.share_of_source_snapshot import ShareOfSourceSnapshot

    snap = (
        db.query(ShareOfSourceSnapshot)
        .filter(ShareOfSourceSnapshot.client_id == client.id)
        .order_by(desc(ShareOfSourceSnapshot.computed_at))
        .first()
    )
    if snap is None or not snap.total_third_party_sources:
        return 0, None, "Not measured yet: run a scan so the sites AI answers draw on are captured."
    pct = float(snap.client_share_pct or 0.0)
    points = max_points * min(pct, _FULL_SOURCE_SHARE_PCT) / _FULL_SOURCE_SHARE_PCT
    evidence = (
        f"Named on {pct:.0f}% of the {snap.total_third_party_sources} independent sites "
        "AI answers drew on in the latest scan."
    )
    hint = None if pct >= _FULL_SOURCE_SHARE_PCT else (
        "Get listed on the sites in the placement list (Authority page) to raise this."
    )
    return points, evidence, hint


def _brand_recognition(client: Client, db: Session, max_points: int):
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult, has_answer
    from app.services.scoring_service import scored_results

    scan = (
        db.query(Scan)
        .filter(Scan.client_id == client.id, Scan.status == "completed")
        .order_by(desc(Scan.completed_at))
        .first()
    )
    rows = []
    if scan is not None:
        rows = [
            r for r in scored_results(
                db.query(ScanQueryResult).filter(
                    ScanQueryResult.scan_id == scan.id,
                    ScanQueryResult.competitor_id.is_(None),
                    ScanQueryResult.category == "brand",
                ).all()
            )
            if not getattr(r, "is_control", False) and has_answer(r)
        ]
    if not rows:
        return 0, None, "Not measured yet: run a scan that includes questions naming the business."
    recognised = sum(1 for r in rows if r.brand_detected)
    evidence = (
        f"AI recognised the business in {recognised} of {len(rows)} answers to "
        "questions that name it."
    )
    return max_points * recognised / len(rows), evidence, None


def _reviews(client: Client, db: Session, max_points: int):
    from app.services import authority_service

    latest = []
    for asset in authority_service.list_assets(client.id, db):
        snaps = asset.review_snapshots or []
        if snaps:
            latest.append(snaps[-1])
    count = sum(int(s.get("count") or 0) for s in latest)
    if not latest or count == 0:
        return 0, None, "No review figures recorded: add rating and count on the Authority page."
    rating = sum(float(s.get("rating") or 0) * int(s.get("count") or 0) for s in latest) / count
    volume_max = max_points - _RATING_POINTS[0][1]
    volume = volume_max * min(1.0, math.log10(count + 1) / math.log10(_FULL_REVIEW_COUNT + 1))
    rating_points = next((p for floor, p in _RATING_POINTS if rating >= floor), 0)
    evidence = f"{count} public reviews averaging {rating:.1f} stars."
    return volume + rating_points, evidence, None


# ── Content Quality ──────────────────────────────────────────────────────────

def _page_readability(client: Client, db: Session, max_points: int):
    from app.models.page_audit import PageAudit

    seen: dict[str, int] = {}
    for audit in (
        db.query(PageAudit)
        .filter(PageAudit.client_id == client.id)
        .order_by(desc(PageAudit.created_at))
        .all()
    ):
        if audit.url not in seen:
            seen[audit.url] = audit.score
        if len(seen) >= _MAX_AUDITED_PAGES:
            break
    if not seen:
        return 0, None, "No pages audited yet: run page audits on 3 or more key pages in Content Production."
    avg = sum(seen.values()) / len(seen)
    evidence = (
        f"Key pages average {avg:.0f}/100 for how easily AI can read and reuse them "
        f"({len(seen)} page{'s' if len(seen) != 1 else ''} checked)."
    )
    hint = "Audit at least 3 key pages for a fair average." if len(seen) < 3 else None
    return max_points * avg / 100, evidence, hint


def _latest_analysis(client: Client, db: Session):
    from app.models.content_analysis import ContentAnalysis

    return (
        db.query(ContentAnalysis)
        .filter(ContentAnalysis.client_id == client.id, ContentAnalysis.status == "completed")
        .order_by(desc(ContentAnalysis.analyzed_at))
        .first()
    )


def _topic_coverage(client: Client, db: Session, max_points: int):
    analysis = _latest_analysis(client, db)
    if analysis is None or not analysis.pages_crawled:
        return 0, None, "Not measured yet: run the content analysis on the Opportunities page."
    coverage = float(analysis.entity_coverage_score or 0.0)
    evidence = f"The website covers {coverage:.0f}% of the topics buyers in this industry ask about."
    return max_points * coverage / 100, evidence, None


def _content_depth(client: Client, db: Session, max_points: int):
    analysis = _latest_analysis(client, db)
    if analysis is None or not analysis.pages_crawled:
        return 0, None, "Not measured yet: run the content analysis on the Opportunities page."
    metrics = analysis.content_metrics_json or {}
    faq = int(metrics.get("faq_count") or 0)
    articles = int(metrics.get("blog_count") or 0)
    per_page = int(metrics.get("word_count") or 0) / analysis.pages_crawled
    # 6 + 7 + 7 = 20, scaled to the criterion's max.
    raw = (6 if faq else 0)
    raw += 7 if articles >= 3 else 4 if articles >= 1 else 0
    raw += 7 if per_page >= _DEEP_WORDS_PER_PAGE else 4 if per_page >= _SOME_WORDS_PER_PAGE else 0
    found = []
    found.append(f"{faq} FAQ section{'s' if faq != 1 else ''}" if faq else "no FAQ section")
    found.append(f"{articles} article{'s' if articles != 1 else ''}" if articles else "no articles")
    found.append(f"about {per_page:.0f} words per page")
    evidence = f"Across {analysis.pages_crawled} pages read: " + ", ".join(found) + "."
    return max_points * raw / 20, evidence, None


_MEASURES = {
    "directory_presence": _directory_presence,
    "ai_source_presence": _ai_source_presence,
    "brand_recognition": _brand_recognition,
    "reviews": _reviews,
    "page_readability": _page_readability,
    "topic_coverage": _topic_coverage,
    "content_depth": _content_depth,
}
