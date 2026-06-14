import pytest

from app.services.url_safety import is_safe_crawl_url


@pytest.mark.parametrize("url", [
    "https://acme.com",
    "http://acme.com/llms.txt",
    "https://www.example.co.uk/robots.txt",
    "example.com",  # scheme defaulted to https
    "https://8.8.8.8/x",  # public IP literal
])
def test_allows_public_urls(url):
    assert is_safe_crawl_url(url) is True


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
