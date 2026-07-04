"""Citation provenance + Share-of-Source (Perplexity-only, v1).

Sources are captured inline during a scan (scan_service). This module owns:
- domain normalization + classification helpers,
- enrich_scan_sources: best-effort post-commit fetch + deterministic brand match,
- compute_share_of_source: the admin read model.
"""
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.competitor import Competitor
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.models.scan_query_source import ScanQuerySource
from app.schemas.provenance import (
    AcquisitionSource,
    BrandShare,
    ShareOfSourceResponse,
    SourcePresence,
)
from app.services.brand_detection import detect_brand_mention
from app.services.url_safety import safe_get, UnsafeUrlError

logger = structlog.get_logger()


def normalize_domain(url: str) -> str:
    """Lowercased host with a leading 'www.' stripped; '' when unparseable."""
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    # A cited source is always a real web host: reject anything with no dot or an
    # embedded space (urlparse keeps "not a url" as the host otherwise).
    if not host or " " in host or "." not in host:
        return ""
    return host[4:] if host.startswith("www.") else host


def classify_source_type(
    domain: str, client_domain: str, competitor_domains: dict[str, str]
) -> str:
    if domain and domain == client_domain:
        return "client_owned"
    if domain in competitor_domains:
        return "competitor_owned"
    return "third_party"


_FETCH_TIMEOUT = 10.0
_MAX_THIRD_PARTY_FETCHES = 60  # hard cap on outbound fetches per scan
_FETCH_WORKERS = 8


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _fetch_page_text(url: str) -> tuple[str, str | None]:
    """Return (fetch_status, text). status is ok/blocked/error; text None unless ok."""
    try:
        resp = safe_get(url, timeout=_FETCH_TIMEOUT)
    except UnsafeUrlError:
        return "blocked", None
    except Exception:
        return "error", None
    ctype = resp.headers.get("content-type", "").lower()
    if resp.status_code != 200 or "html" not in ctype:
        return "error", None
    return "ok", _extract_text(resp.text)


def enrich_scan_sources(scan_id: uuid.UUID, db: Session) -> None:
    """Classify + brand-match every captured source for a scan's client queries.

    Best-effort and idempotent-ish: only rows still 'pending' are processed.
    Owned domains are classified without a fetch; third-party pages are fetched
    once each (deduped by URL) through the SSRF-guarded crawler and matched with
    detect_brand_mention. Blocked/errored fetches fail open (present_brands None).
    """
    rows = (
        db.query(ScanQuerySource)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == scan_id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQuerySource.fetch_status == "pending",
        )
        .all()
    )
    if not rows:
        return

    scan = db.get(Scan, scan_id)
    client = db.get(Client, scan.client_id) if scan else None
    if client is None:
        return
    competitors = db.query(Competitor).filter(Competitor.client_id == client.id).all()

    client_domain = normalize_domain(client.website or "")
    competitor_domains = {
        normalize_domain(c.website): str(c.id) for c in competitors if c.website
    }
    comp_by_id = {str(c.id): c for c in competitors}

    by_url: dict[str, list[ScanQuerySource]] = defaultdict(list)
    for row in rows:
        by_url[row.url].append(row)

    third_party_urls: list[str] = []
    for url, occurrences in by_url.items():
        domain = normalize_domain(url)
        stype = classify_source_type(domain, client_domain, competitor_domains)
        for row in occurrences:
            row.source_type = stype
        if stype == "client_owned":
            for row in occurrences:
                row.fetch_status = "ok"
                row.present_brands = {"client": True, "competitors": []}
        elif stype == "competitor_owned":
            comp_id = competitor_domains[domain]
            for row in occurrences:
                row.fetch_status = "ok"
                row.present_brands = {"client": False, "competitors": [comp_id]}
        else:
            third_party_urls.append(url)

    third_party_urls = third_party_urls[:_MAX_THIRD_PARTY_FETCHES]
    fetched: dict[str, tuple[str, str | None]] = {}
    if third_party_urls:
        with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
            for url, outcome in zip(
                third_party_urls, pool.map(_fetch_page_text, third_party_urls)
            ):
                fetched[url] = outcome

    for url in third_party_urls:
        status, text = fetched.get(url, ("error", None))
        occurrences = by_url[url]
        if status != "ok" or text is None:
            for row in occurrences:
                row.fetch_status = status
            continue
        present = {
            "client": detect_brand_mention(text, client.name),
            "competitors": [
                cid for cid, c in comp_by_id.items() if detect_brand_mention(text, c.name)
            ],
        }
        for row in occurrences:
            row.fetch_status = "ok"
            row.present_brands = present

    db.commit()
    logger.info(
        "scan_sources_enriched",
        scan_id=str(scan_id),
        total=len(rows),
        third_party_fetched=len(third_party_urls),
    )


def _empty_share(last_scan_at: str | None) -> ShareOfSourceResponse:
    return ShareOfSourceResponse(
        last_scan_at=last_scan_at,
        total_third_party_sources=0,
        client_share=None,
        competitor_shares=[],
        acquisition_list=[],
        flip_targets=[],
    )


def compute_share_of_source(client_id: uuid.UUID, db: Session) -> ShareOfSourceResponse:
    """Admin read model: Share-of-Source + acquisition list from the latest scan.

    Denominator is the count of unique third-party source URLs (fetch_status ok)
    cited by the client's own queries. A URL cited N times counts once for share
    but its N citations drive acquisition-list ranking.
    """
    latest = (
        db.query(Scan)
        .filter(Scan.client_id == client_id, Scan.status == "completed")
        .order_by(Scan.completed_at.desc())
        .first()
    )
    if not latest:
        return _empty_share(None)
    last_scan_at = latest.completed_at.isoformat() + "Z" if latest.completed_at else None

    rows = (
        db.query(ScanQuerySource)
        .join(ScanQueryResult, ScanQueryResult.id == ScanQuerySource.scan_query_result_id)
        .filter(
            ScanQueryResult.scan_id == latest.id,
            ScanQueryResult.competitor_id.is_(None),
            ScanQuerySource.source_type == "third_party",
            ScanQuerySource.fetch_status == "ok",
        )
        .all()
    )
    if not rows:
        return _empty_share(last_scan_at)

    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()
    comp_names = {str(c.id): c.name for c in competitors}
    client = db.get(Client, client_id)

    # Collapse occurrences to unique URLs; presence is identical across a URL's rows.
    unique: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.url] = counts.get(row.url, 0) + 1
        if row.url not in unique:
            unique[row.url] = {
                "domain": row.domain,
                "title": row.title,
                "present": row.present_brands or {"client": False, "competitors": []},
            }
    denom = len(unique)

    client_present = sum(1 for u in unique.values() if u["present"].get("client"))
    comp_present_counts: dict[str, int] = {cid: 0 for cid in comp_names}
    for u in unique.values():
        for cid in u["present"].get("competitors", []):
            if cid in comp_present_counts:
                comp_present_counts[cid] += 1

    def pct(n: int) -> float:
        return round(n / denom * 100, 1) if denom else 0.0

    client_share = BrandShare(
        competitor_id=None,
        name=client.name if client else "You",
        sources_present=client_present,
        share_pct=pct(client_present),
    )
    competitor_shares = [
        BrandShare(
            competitor_id=uuid.UUID(cid),
            name=comp_names[cid],
            sources_present=n,
            share_pct=pct(n),
        )
        for cid, n in sorted(comp_present_counts.items(), key=lambda kv: -kv[1])
    ]

    acquisition = []
    for url, meta in unique.items():
        present = meta["present"]
        comp_ids = [cid for cid in present.get("competitors", []) if cid in comp_names]
        if not present.get("client") and comp_ids:
            acquisition.append(
                AcquisitionSource(
                    url=url,
                    domain=meta["domain"],
                    title=meta["title"],
                    citation_count=counts[url],
                    competitors_present=[
                        SourcePresence(competitor_id=uuid.UUID(cid), name=comp_names[cid])
                        for cid in comp_ids
                    ],
                )
            )
    acquisition.sort(key=lambda a: -a.citation_count)

    return ShareOfSourceResponse(
        last_scan_at=last_scan_at,
        total_third_party_sources=denom,
        client_share=client_share,
        competitor_shares=competitor_shares,
        acquisition_list=acquisition,
        flip_targets=acquisition[:3],
    )
