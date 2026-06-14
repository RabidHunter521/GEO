"""SSRF guard for outbound crawls.

Blocks the realistic threats from an admin pasting an internal address as a
client website: localhost-style hostnames and private/loopback/link-local IP
literals (incl. the cloud metadata range). It does not resolve DNS, so it won't
catch a public hostname that points at an internal IP (DNS rebinding) — out of
scope for trusted, admin-entered input.
"""
import ipaddress
from urllib.parse import urlparse

_BLOCKED_HOST_SUFFIXES = (".localhost", ".internal", ".local")


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
