"""Placement engine: third-party pages AI answers draw on that don't name the
client, turned into a ranked, worked list (docs/superpowers/plans/
2026-10-02-placement-engine.md).

This module owns discovery (refresh_targets, run after every scan), the
deterministic priority score, and the target lifecycle. It reads only what
provenance enrichment already recorded -- no fetches happen here.
"""
import math
import re
import uuid
from collections import defaultdict
from urllib.parse import urljoin

import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.constants import (
    PLACEMENT_CATEGORY_WEIGHTS,
    PLACEMENT_REACH_SATURATION,
    PLACEMENT_STALE_AFTER_SCANS,
    PLATFORM_LABELS,
)
from app.core.time import utcnow
from app.models.authority_asset import AuthorityAsset
from app.models.competitor import Competitor
from app.models.placement_target import PlacementTarget
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.services.brand_detection import detect_brand_mention
from app.services.provenance_service import normalize_domain
from app.services.url_safety import UnsafeUrlError, safe_get

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


_BUYER_CATEGORIES = {"recommendation", "local", "comparison"}
_CATEGORY_NOTES = {
    "directory": "directory (usually a simple submission)",
    "listicle": "listicle (editors update round-ups)",
    "news": "news (needs a story angle)",
    "other": "other page",
    "marketplace": "marketplace (needs a seller listing)",
    "review": "review site (worked through reviews, not outreach)",
    "social": "social (needs an active profile)",
    "reference": "reference (hard to influence)",
}
# Factor weights; they sum to 1 before the category multiplier.
_W_REACH, _W_BREADTH, _W_INTENT, _W_COMPETITION, _W_RECENCY = 0.35, 0.20, 0.15, 0.15, 0.15


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def score_target(target: PlacementTarget) -> tuple[int, list[str]]:
    """Deterministic 0-100 priority from stored evidence, with the reasons
    that produced it. No model call: the ranking must be explainable and
    reproducible from the row alone."""
    answers = target.answers_count or 0
    platforms = list(target.platforms or [])
    categories = set(target.query_categories or [])
    competitors = len(target.competitors_present or [])
    others = target.other_businesses_listed or 0
    missing = target.scans_missing or 0
    reasons: list[str] = []

    reach = min(1.0, math.log2(1 + answers) / math.log2(1 + PLACEMENT_REACH_SATURATION))
    reasons.append(f"{_plural(answers, 'answer')} drew on this page in the latest scan")

    breadth = len(platforms) / len(PLATFORM_LABELS)
    names = ", ".join(PLATFORM_LABELS.get(p, p) for p in platforms)
    reasons.append(f"Used by {len(platforms)} of {len(PLATFORM_LABELS)} AI platforms ({names})")

    buyer = sorted(categories & _BUYER_CATEGORIES)
    if buyer:
        intent = 1.0
        reasons.append(f"Answers buyer questions ({', '.join(buyer)})")
    else:
        intent = 0.4
        reasons.append("Only answers brand questions")

    if competitors:
        competition = 1.0
        reasons.append(f"{_plural(competitors, 'tracked competitor')} listed here, not you")
    elif others:
        competition = 0.6
        reasons.append(f"Lists {others} other businesses, not you")
    else:
        competition = 0.3

    recency = max(0.0, 1 - missing / PLACEMENT_STALE_AFTER_SCANS)
    if missing:
        reasons.append(f"Not seen in the last {_plural(missing, 'scan')}")

    weight = PLACEMENT_CATEGORY_WEIGHTS.get(target.category, PLACEMENT_CATEGORY_WEIGHTS["other"])
    reasons.append(f"Category: {_CATEGORY_NOTES.get(target.category, target.category)}")

    raw = (
        _W_REACH * reach + _W_BREADTH * breadth + _W_INTENT * intent
        + _W_COMPETITION * competition + _W_RECENCY * recency
    )
    return round(100 * weight * raw), reasons


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

    for target in existing.values():
        target.priority_score, target.priority_reasons = score_target(target)

    db.commit()
    logger.info(
        "placement_targets_refreshed",
        scan_id=str(scan_id),
        client_id=str(client_id),
        pages=len(by_url),
    )



# ── page analysis (on demand) ───────────────────────────────────────────────

_NUMBERED_ENTRY = re.compile(r"^\s*#?\s*(\d{1,3})\s*[.):\-–]\s*(.+)$")
_CONTACT = re.compile(r"contact|get[- ]in[- ]touch|write[- ]for[- ]us|advertis", re.IGNORECASE)
_SUBMISSION = re.compile(
    r"suggest[- ]?a[- ]?business|add[- ]?your[- ]?business|list[- ]?your[- ]?business"
    r"|add[- ]?(a[- ]?)?listing|claim[- ]?(a[- ]?)?listing|get[- ]?listed|submit",
    re.IGNORECASE,
)
_MIN_LIST_ENTRIES = 3
_MAX_ENTRIES_KEPT = 20
_ANALYSIS_TIMEOUT = 10.0


def _meta(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str | None:
    tag = soup.find("meta", attrs={"name": name} if name else {"property": prop})
    content = tag.get("content") if tag else None
    return content.strip() if isinstance(content, str) and content.strip() else None


def _date(value: str | None) -> str | None:
    return value[:10] if value and re.match(r"\d{4}-\d{2}-\d{2}", value) else None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _entries(soup: BeautifulSoup) -> list[str]:
    """Ranked entries: numbered h2/h3 headings, else items of an ordered list."""
    numbered = []
    for heading in soup.find_all(["h2", "h3"]):
        match = _NUMBERED_ENTRY.match(heading.get_text(" ", strip=True))
        if match:
            numbered.append(match.group(2).strip())
    if len(numbered) >= _MIN_LIST_ENTRIES:
        return numbered
    for ol in soup.find_all("ol"):
        items = [li.get_text(" ", strip=True)[:120] for li in ol.find_all("li", recursive=False)]
        if len(items) >= _MIN_LIST_ENTRIES:
            return items
    return []


def analyze_page(html: str, base_url: str, competitors: list[tuple[str, str]]) -> dict:
    """Deterministic read of a page: is it a ranked list, who is on it, how to
    reach the people who maintain it. `competitors` is [(id, name)].

    Contact details are only what the page itself publishes, and are for the
    admin's outreach -- never shown on a client surface."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)

    entries = _entries(soup)
    is_listicle = bool(entries)
    listed = []
    for comp_id, name in competitors:
        if not detect_brand_mention(text, name):
            continue
        position = next(
            (i for i, entry in enumerate(entries, start=1) if detect_brand_mention(entry, name)),
            None,
        )
        listed.append({"competitor_id": comp_id, "name": name, "position": position})
    in_list = sum(1 for c in listed if c["position"] is not None)

    emails, contact_pages, submissions = [], [], []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = f"{a.get_text(' ', strip=True)} {href}"
        if href.lower().startswith("mailto:"):
            address = href[7:].split("?")[0].strip().lower()
            if "@" in address:
                emails.append(address)
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if _SUBMISSION.search(label):
            submissions.append(absolute)
        elif _CONTACT.search(label):
            contact_pages.append(absolute)

    time_tag = soup.find("time", attrs={"datetime": True})
    return {
        "title": soup.title.get_text(strip=True)[:300] if soup.title else None,
        "is_listicle": is_listicle,
        "entries_count": len(entries),
        "entries": entries[:_MAX_ENTRIES_KEPT],
        "competitors_listed": listed,
        "other_businesses_listed": max(0, len(entries) - in_list) if is_listicle else None,
        "author": _meta(soup, name="author"),
        "site_name": _meta(soup, prop="og:site_name"),
        "published": _date(_meta(soup, prop="article:published_time"))
        or _date(time_tag.get("datetime") if time_tag else None),
        "modified": _date(_meta(soup, prop="article:modified_time")),
        "contact": {
            "emails": _dedupe(emails),
            "contact_pages": _dedupe(contact_pages),
            "submission_links": _dedupe(submissions),
        },
    }


def _fetch_html(url: str):
    """(status, response) where status is ok | blocked | error."""
    try:
        resp = safe_get(url, timeout=_ANALYSIS_TIMEOUT)
    except UnsafeUrlError:
        return "blocked", None
    except Exception:
        return "error", None
    if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "").lower():
        return "error", None
    return "ok", resp


def analyze_target(target: PlacementTarget, db: Session) -> PlacementTarget:
    """Fetch and analyse a target's page (at most 2 fetches: the page, then
    one same-site contact page only if the page itself shows no email).
    Fails open: an unreachable page records its fetch status and nothing else."""
    status, resp = _fetch_html(target.url)
    target.analyzed_at = utcnow()
    if status != "ok":
        target.page_analysis = {"fetch_status": status}
        db.commit()
        return target

    competitors = [
        (str(c.id), c.name)
        for c in db.query(Competitor).filter(Competitor.client_id == target.client_id).all()
    ]
    final_url = resp.url or target.url
    analysis = analyze_page(resp.text, final_url, competitors)
    analysis["fetch_status"] = "ok"

    contact = analysis["contact"]
    if not contact["emails"]:
        site = normalize_domain(final_url)
        page = next((p for p in contact["contact_pages"] if normalize_domain(p) == site), None)
        if page:
            c_status, c_resp = _fetch_html(page)
            if c_status == "ok":
                contact["emails"] = analyze_page(c_resp.text, page, [])["contact"]["emails"]

    target.page_analysis = analysis
    if analysis["other_businesses_listed"] is not None:
        target.other_businesses_listed = analysis["other_businesses_listed"]
    target.priority_score, target.priority_reasons = score_target(target)
    db.commit()
    logger.info("placement_page_analyzed", target_id=str(target.id), listicle=analysis["is_listicle"])
    return target


# ── admin read model + manual status ────────────────────────────────────────

class PlacementTransitionError(ValueError):
    """A manual status change that would skip delivery or proof."""


# Only these can be changed by hand; pursuing/placed/verified come from
# delivery (Outcome Actions) and proof.
_MANUAL_FROM = {"open", "stale", "dismissed"}


def set_status(target: PlacementTarget, status: str, db: Session) -> PlacementTarget:
    if target.status not in _MANUAL_FROM:
        raise PlacementTransitionError(
            f"A {target.status} placement is managed through its delivery item"
        )
    target.status = status
    db.commit()
    return target


def _competitor_names(client_id: uuid.UUID, db: Session) -> dict[str, str]:
    return {
        str(c.id): c.name
        for c in db.query(Competitor).filter(Competitor.client_id == client_id).all()
    }


def _summary(target: PlacementTarget, names: dict[str, str]) -> dict:
    return {
        "id": target.id,
        "url": target.url,
        "domain": target.domain,
        "title": target.title,
        "category": target.category,
        "status": target.status,
        "answers_count": target.answers_count,
        "platforms": target.platforms or [],
        "query_categories": target.query_categories or [],
        "competitors": [names[c] for c in (target.competitors_present or []) if c in names],
        "other_businesses_listed": target.other_businesses_listed,
        "client_present": target.client_present,
        "priority_score": target.priority_score,
        "priority_reasons": target.priority_reasons or [],
        "authority_asset_id": target.authority_asset_id,
        "outcome_action_id": target.outcome_action_id,
        "last_seen_at": target.last_seen_at,
        "analyzed_at": target.analyzed_at,
    }


def list_targets(client_id: uuid.UUID, db: Session) -> list[dict]:
    """Every target for the client, highest priority first (the UI filters by
    status). Light rows: analysis, drafts and the proof question are on the
    detail read."""
    names = _competitor_names(client_id, db)
    targets = (
        db.query(PlacementTarget)
        .filter(PlacementTarget.client_id == client_id)
        .order_by(PlacementTarget.priority_score.desc(), PlacementTarget.created_at.asc())
        .all()
    )
    return [_summary(t, names) for t in targets]


def target_detail(target: PlacementTarget, db: Session) -> dict:
    data = _summary(target, _competitor_names(target.client_id, db))
    proof = db.get(ScanQueryResult, target.representative_result_id) if target.representative_result_id else None
    data.update(
        page_analysis=target.page_analysis,
        outreach_drafts=target.outreach_drafts or [],
        proof_question=(
            {"query_text": proof.query_text, "platform": proof.platform} if proof else None
        ),
    )
    return data
