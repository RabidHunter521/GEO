"""SSRF guard for outbound crawls.

Blocks the realistic threats from an admin pasting an internal address as a
client website: localhost-style hostnames and private/loopback/link-local IP
literals (incl. the cloud metadata range). It does not resolve DNS, so it won't
catch a public hostname that points at an internal IP (DNS rebinding) — out of
scope for trusted, admin-entered input.
"""
import ipaddress
import json
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


def is_safe_crawl_url(url: str) -> bool:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        return False
    # If the host is an IP literal, reject non-public ranges.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a hostname (trusted admin input) — allow
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


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
