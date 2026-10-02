"""Placement engine: third-party pages AI answers draw on that don't name the
client, turned into a ranked, worked list (docs/superpowers/plans/
2026-10-02-placement-engine.md).

This module owns discovery (refresh_targets, run after every scan), the
deterministic priority score, and the target lifecycle. It reads only what
provenance enrichment already recorded -- no fetches happen here.
"""
import re
import uuid
from collections import defaultdict

import structlog
from sqlalchemy.orm import Session

from app.core.constants import PLACEMENT_STALE_AFTER_SCANS
from app.core.time import utcnow
from app.models.authority_asset import AuthorityAsset
from app.models.placement_target import PlacementTarget
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource

logger = structlog.get_logger()

# Buyer questions make the strongest proof that a placement worked; a brand
# question ("tell me about Acme") says little about being recommended.
_PROOF_PREFERENCE = {"recommendation": 0, "local": 1, "comparison": 2, "brand": 3}

# classify_domain_category buckets -> placement categories.
_CATEGORY_MAP = {
    "directory": "directory",
    "news": "news",
    "review": "review",
    "social": "social",
    "marketplace": "marketplace",
    "reference": "reference",
    "government": "reference",
}
_LISTICLE_WORDS = re.compile(r"\b(best|top)\b", re.IGNORECASE)
_LISTICLE_SHAPE = re.compile(r"\b\d{1,3}\b|\b(in|near|for)\b", re.IGNORECASE)
# Only these buckets can be re-read as a listicle from the page title; a
# directory or review site stays what it is.
_LISTICLE_OVERRIDABLE = {"other", "news"}

_TITLE_MAX = 500


def categorize(domain: str, title: str | None) -> str:
    """Placement category for a page: the domain heuristic, upgraded to
    "listicle" when the title reads like a ranked round-up ("10 Best Dentists
    in KL", "Top 7 clinics near Bangsar")."""
    from app.services.market_intelligence_service import classify_domain_category

    category = _CATEGORY_MAP.get(classify_domain_category(domain or ""), "other")
    if (
        category in _LISTICLE_OVERRIDABLE
        and title
        and _LISTICLE_WORDS.search(title)
        and _LISTICLE_SHAPE.search(title)
    ):
        return "listicle"
    return category


def _matching_asset(domain: str, assets: list[AuthorityAsset]) -> AuthorityAsset | None:
    from app.services.authority_service import _domain_matches

    bare = domain[4:] if domain.startswith("www.") else domain
    for asset in assets:
        if _domain_matches(bare, asset.provenance_domain):
            return asset
    return None


def refresh_targets(scan_id: uuid.UUID, client_id: uuid.UUID, db: Session) -> None:
    """Upsert placement targets from one completed scan's checked sources.

    A target is a third-party page (enrichment fetched it: fetch_status ok)
    that a client-owned answer drew on while the page did not name the client.
    Evidence fields describe the latest scan the page appeared in. Pages that
    now name the client are recorded (client_present) but never created.
    Targets absent from PLACEMENT_STALE_AFTER_SCANS consecutive scans go
    stale; a scan with no checked sources at all ages nothing, so a failed
    enrichment cannot stale the whole list. Dismissed targets stay dismissed.
    """
    rows = (
        db.query(ScanQuerySource, ScanQueryResult)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQueryResult.is_control.is_(False),
            ScanQuerySource.source_type == "third_party",
            ScanQuerySource.fetch_status == "ok",
        )
        .all()
    )
    if not rows:
        return

    by_url: dict[str, list[tuple[ScanQuerySource, ScanQueryResult]]] = defaultdict(list)
    for source, result in rows:
        by_url[source.url].append((source, result))

    existing = {
        t.url: t
        for t in db.query(PlacementTarget).filter(PlacementTarget.client_id == client_id).all()
    }
    assets = (
        db.query(AuthorityAsset)
        .filter(AuthorityAsset.client_id == client_id, AuthorityAsset.hidden.is_(False))
        .all()
    )
    now = utcnow()
    seen_urls: set[str] = set()

    for url, pairs in by_url.items():
        client_on_page = any((s.present_brands or {}).get("client") for s, _ in pairs)
        target = existing.get(url)
        if client_on_page:
            if target is not None:
                target.client_present = True
                target.last_seen_scan_id = scan_id
                target.last_seen_at = now
                target.scans_missing = 0
                seen_urls.add(url)
            continue

        source0 = pairs[0][0]
        if target is None:
            target = PlacementTarget(
                client_id=client_id,
                url=url,
                domain=source0.domain,
                category="other",
                first_seen_scan_id=scan_id,
            )
            db.add(target)
            existing[url] = target
        seen_urls.add(url)

        title = next((s.title for s, _ in pairs if s.title), None)
        if title:
            target.title = title[:_TITLE_MAX]
        target.category = categorize(target.domain, target.title)

        results = {r.id: r for _, r in pairs}.values()
        target.answers_count = len(results)
        target.platforms = sorted({r.platform for r in results})
        target.query_categories = sorted({r.category for r in results})
        target.competitors_present = sorted({
            cid for s, _ in pairs for cid in (s.present_brands or {}).get("competitors", [])
        })
        unseen = [r for r in results if not r.brand_detected]
        if unseen:
            best = min(
                unseen,
                key=lambda r: (_PROOF_PREFERENCE.get(r.category, 9), -(r.created_at.timestamp() if r.created_at else 0)),
            )
            target.representative_result_id = best.id
        target.client_present = False
        target.last_seen_scan_id = scan_id
        target.last_seen_at = now
        target.scans_missing = 0
        if target.status == "stale":
            target.status = "open"
        asset = _matching_asset(target.domain, assets)
        target.authority_asset_id = asset.id if asset else None

    for url, target in existing.items():
        if url in seen_urls or target.status == "dismissed":
            continue
        target.scans_missing += 1
        if target.status == "open" and target.scans_missing >= PLACEMENT_STALE_AFTER_SCANS:
            target.status = "stale"

    db.commit()
    logger.info(
        "placement_targets_refreshed",
        scan_id=str(scan_id),
        client_id=str(client_id),
        pages=len(by_url),
    )

