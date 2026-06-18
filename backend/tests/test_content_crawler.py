from unittest.mock import MagicMock, patch

from app.services.content_crawler import (
    _domain_base,
    crawl_site,
    discover_pages,
)


def _resp(status=200, text="", content_type="text/html"):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = {"content-type": content_type}
    return m


def test_domain_base_strips_path_and_adds_scheme():
    assert _domain_base("acme.com/about") == "https://acme.com"


def test_discover_pages_includes_homepage_and_caps_at_15():
    locs = "".join(f"<loc>https://acme.com/p{i}</loc>" for i in range(30))
    sitemap = _resp(text=f"<urlset>{locs}</urlset>")

    with patch("app.services.content_crawler.safe_get", return_value=sitemap):
        pages = discover_pages("https://acme.com")

    assert pages[0] == "https://acme.com"
    assert len(pages) == 15


def test_discover_pages_skips_external_domains():
    sitemap = _resp(
        text="<urlset><loc>https://acme.com/a</loc><loc>https://evil.com/b</loc></urlset>"
    )
    with patch("app.services.content_crawler.safe_get", return_value=sitemap):
        pages = discover_pages("https://acme.com")

    assert "https://evil.com/b" not in pages
    assert "https://acme.com/a" in pages


def test_discover_pages_survives_missing_sitemap():
    with patch("app.services.content_crawler.safe_get", side_effect=Exception("404")):
        pages = discover_pages("https://acme.com")
    assert pages == ["https://acme.com"]


def test_crawl_site_aggregates_metrics():
    def dispatch(url, **kwargs):
        if url.endswith("/sitemap.xml"):
            return _resp(
                text="<urlset>"
                "<loc>https://acme.com/blog/post-1</loc>"
                "<loc>https://acme.com/faq</loc>"
                "</urlset>"
            )
        if "faq" in url:
            return _resp(
                text="<html><body><h1>Help</h1><h2>FAQ</h2>"
                "<script type='application/ld+json'>{}</script>"
                "<p>Frequently asked answers</p></body></html>"
            )
        return _resp(
            text="<html><body><h1>Welcome</h1>"
            "<p>We sell solar panels and inverters</p></body></html>"
        )

    with patch("app.services.content_crawler.safe_get", side_effect=dispatch):
        result = crawl_site("https://acme.com")

    # homepage + blog post + faq page
    assert result.pages_crawled == 3
    assert result.h1_count == 3
    assert result.faq_count == 1
    assert result.blog_count == 1
    assert result.schema_present is True
    assert result.word_count > 0


def test_crawl_site_skips_non_html_and_errors():
    def dispatch(url, **kwargs):
        if url.endswith("/sitemap.xml"):
            return _resp(text="<urlset><loc>https://acme.com/data.json</loc></urlset>")
        if "data.json" in url:
            return _resp(text="{}", content_type="application/json")
        return _resp(text="<html><body><h1>Home</h1></body></html>")

    with patch("app.services.content_crawler.safe_get", side_effect=dispatch):
        result = crawl_site("https://acme.com")

    # only the homepage counts; the JSON page is skipped
    assert result.pages_crawled == 1
    assert result.schema_present is False
