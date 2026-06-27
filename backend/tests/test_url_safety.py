import socket

import pytest

from app.services import url_safety
from app.services.url_safety import is_safe_crawl_url


def _fake_getaddrinfo(ip: str):
    """Build a getaddrinfo stub that resolves every hostname to `ip`, so the
    DNS-resolving SSRF check is deterministic and offline (no live lookups)."""
    def _resolver(host, port, *args, **kwargs):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]
    return _resolver


@pytest.fixture(autouse=True)
def _resolve_public(monkeypatch):
    """Default: hostnames resolve to a public IP. Tests that need a specific
    resolution (private / unresolvable) override this within the test body."""
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))


@pytest.mark.parametrize("url", [
    "https://acme.com",
    "http://acme.com/llms.txt",
    "https://www.example.co.uk/robots.txt",
    "example.com",  # scheme defaulted to https
    "https://8.8.8.8/x",  # public IP literal (bypasses DNS)
])
def test_allows_public_urls(url):
    assert is_safe_crawl_url(url) is True


def test_blocks_public_hostname_resolving_to_metadata_ip(monkeypatch):
    # The DNS-rebinding / internal-pointer case the literal check alone misses.
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    assert is_safe_crawl_url("https://totally-legit.com/latest/meta-data") is False


def test_blocks_public_hostname_resolving_to_private_ip(monkeypatch):
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.5"))
    assert is_safe_crawl_url("https://intranet-proxy.example.com") is False


def test_blocks_unresolvable_hostname(monkeypatch):
    def _boom(*args, **kwargs):
        raise socket.gaierror("name resolution failed")
    monkeypatch.setattr(url_safety.socket, "getaddrinfo", _boom)
    assert is_safe_crawl_url("https://does-not-resolve.invalid") is False


@pytest.mark.parametrize("url", [
    "http://localhost/llms.txt",
    "http://app.localhost",
    "http://printer.local",
    "http://db.internal/x",
    "http://127.0.0.1",
    "http://10.0.0.5/x",
    "http://192.168.1.1",
    "http://172.16.0.1",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://[::1]/x",  # IPv6 loopback
    "http://0.0.0.0",
    "ftp://acme.com",  # non-http scheme
    "file:///etc/passwd",
    "",
])
def test_blocks_internal_and_non_http(url):
    assert is_safe_crawl_url(url) is False
