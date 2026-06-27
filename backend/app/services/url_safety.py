"""SSRF guard for outbound crawls.

Blocks a client website (admin-entered, but the trust boundary is "whoever can
set a client's website") from pointing the crawler at internal infrastructure:
localhost-style hostnames, private/loopback/link-local IP literals (incl. the
cloud metadata range), AND public hostnames that *resolve* to those ranges. The
host is resolved with getaddrinfo and every returned address is checked, so a
DNS name pointing at 169.254.169.254 or 10.x is rejected.

This narrows but does not fully eliminate TOCTOU DNS rebinding: the connection's
own resolution can differ from this pre-check. Full closure would require pinning
the validated IP into the socket; for this threat model resolve-and-check is the
deliberate cost/benefit point.
"""
import ipaddress
import json
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

_BLOCKED_HOST_SUFFIXES = (".localhost", ".internal", ".local")

# Bound how much of a page we ever pull into memory, and how many redirect hops
# we follow. A multi-GB page must not OOM a worker, and every hop is re-checked
# for SSRF (a public URL can 302 to 169.254.169.254).
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_MAX_REDIRECTS = 5


class UnsafeUrlError(RuntimeError):
    """A requested URL (or a redirect target) failed the SSRF safety check."""


@dataclass
class SafeResponse:
    status_code: int
    text: str = ""
    headers: dict = field(default_factory=dict)

    def json(self):
        return json.loads(self.text)


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    """Reject any non-publicly-routable address (private, loopback, link-local
    incl. the 169.254 cloud-metadata range, reserved, multicast, unspecified)."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_crawl_url(url: str) -> bool:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    # IP literal: check it directly, no DNS needed.
    try:
        return not _ip_is_blocked(ipaddress.ip_address(host))
    except ValueError:
        pass  # not a literal — it's a hostname; resolve and check below.
    # Hostname: resolve to every A/AAAA address and reject if ANY lands in a
    # non-public range (a public name can still point at an internal IP).
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False  # unresolvable — treat as unsafe rather than connect blind
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if _ip_is_blocked(ip):
            return False
    return True


def safe_get(
    url: str,
    *,
    timeout: float,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_redirects: int = _MAX_REDIRECTS,
) -> SafeResponse:
    """GET a URL with SSRF-safe redirect handling and a bounded body.

    Redirects are followed manually so every hop is re-checked with
    is_safe_crawl_url (httpx's own follow_redirects would skip that check, so a
    public host could redirect into the private range). The body is streamed and
    truncated at max_bytes so a huge page can't exhaust memory. Raises
    UnsafeUrlError when a hop is unsafe; other httpx errors propagate to the
    caller (the crawlers already treat any exception as "skip / not verified").
    """
    current = url
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        for _ in range(max_redirects + 1):
            if not is_safe_crawl_url(current):
                raise UnsafeUrlError(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(str(resp.url), resp.headers["location"])
                    continue
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) >= max_bytes:
                        break
                encoding = resp.encoding or "utf-8"
                text = bytes(body[:max_bytes]).decode(encoding, errors="replace")
                return SafeResponse(
                    status_code=resp.status_code,
                    text=text,
                    headers=dict(resp.headers),
                )
    raise UnsafeUrlError(f"too many redirects: {url}")
