"""Citation provenance + Share-of-Source (Perplexity-only, v1).

Sources are captured inline during a scan (scan_service). This module owns:
- domain normalization + classification helpers,
- enrich_scan_sources: best-effort post-commit fetch + deterministic brand match,
- compute_share_of_source: the admin read model.
"""
from urllib.parse import urlparse

import structlog

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
