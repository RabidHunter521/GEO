"""site_audit_service tests — mocked safe_get with HTML/XML fixtures (spec §10)."""
from datetime import datetime, timedelta, UTC
from unittest.mock import patch
from urllib.parse import urlparse

import httpx

from app.services.url_safety import SafeResponse

_RECENT = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d")
_STALE = (datetime.now(UTC) - timedelta(days=300)).strftime("%Y-%m-%d")

HEALTHY_HTML = (
    "<html><head>"
    "<title>Acme Dental Clinic Kuala Lumpur</title>"
    '<meta name="description" content="Acme Dental Clinic provides gentle, affordable dental care '
    'for families in Kuala Lumpur, from checkups to braces and implants.">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<link rel="canonical" href="https://acme.com/">'
    '<meta property="og:title" content="Acme Dental Clinic">'
    '<meta property="og:description" content="Gentle dental care in KL">'
    '<meta property="og:image" content="https://acme.com/logo.png">'
    '<script type="application/ld+json">'
    '{"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": "Acme"}]}'
    "</script></head><body>"
    "<h1>Welcome to Acme Dental</h1><h2>Our Services</h2><h3>Braces</h3><h2>Contact</h2>"
    + "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(12))
    + "</body></html>"
)

HEALTHY_ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://acme.com/sitemap.xml\n"

HEALTHY_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<url><loc>https://acme.com/</loc><lastmod>{_RECENT}</lastmod></url>"
    "<url><loc>https://acme.com/services</loc></url>"
    "</urlset>"
)

SITEMAP_INDEX_STALE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<sitemap><loc>https://acme.com/sitemap-pages.xml</loc><lastmod>{_STALE}</lastmod></sitemap>"
    "</sitemapindex>"
)

BLOCKING_ROBOTS = (
    "User-agent: GPTBot\nDisallow: /\n\n"
    "User-agent: ClaudeBot\nDisallow: /\n\n"
    "User-agent: *\nAllow: /\n\nSitemap: https://acme.com/sitemap.xml\n"
)

_HEALTHY_ROUTES = {
    "/": SafeResponse(200, HEALTHY_HTML),
    "/robots.txt": SafeResponse(200, HEALTHY_ROBOTS),
    "/llms.txt": SafeResponse(200, "# Acme Dental Clinic\n> Gentle dental care"),
    "/llms-full.txt": SafeResponse(200, "# Acme Dental Clinic — full\ndetails"),
    "/sitemap.xml": SafeResponse(200, HEALTHY_SITEMAP),
}


def _fake_safe_get(routes):
    def _get(url, **kwargs):
        path = urlparse(url).path or "/"
        result = routes.get(path, SafeResponse(404))
        if isinstance(result, Exception):
            raise result
        return result
    return _get


def _run(routes, http_redirects=True):
    from app.services import site_audit_service
    with patch.object(site_audit_service, "is_safe_crawl_url", return_value=True), \
         patch.object(site_audit_service, "safe_get", side_effect=_fake_safe_get(routes)), \
         patch.object(site_audit_service, "_http_redirects_to_https", return_value=http_redirects):
        return site_audit_service.run_site_audit("https://acme.com")


def _by_id(checks):
    return {c["id"]: c for c in checks}


# 1. Fully healthy fixture site → 19 passes.
def test_healthy_site_all_19_pass():
    checks = _run(_HEALTHY_ROUTES)
    assert len(checks) == 19
    non_pass = [c["id"] for c in checks if c["status"] != "pass"]
    assert non_pass == []
    # every check carries the full shape
    for c in checks:
        assert set(c) == {"id", "label", "status", "detail", "fix"}
        assert c["fix"] == ""  # empty when pass


# 2. robots.txt disallowing GPTBot + ClaudeBot → robots_ai_bots fail names both bots.
def test_blocked_bots_named_in_fail():
    routes = dict(_HEALTHY_ROUTES)
    routes["/robots.txt"] = SafeResponse(200, BLOCKING_ROBOTS)
    c = _by_id(_run(routes))["robots_ai_bots"]
    assert c["status"] == "fail"
    assert "GPTBot" in c["detail"] and "ClaudeBot" in c["detail"]
    assert c["fix"] != ""


# 3. Missing sitemap, missing canonical, two H1s, no viewport → correct statuses + fixes.
def test_degraded_page_statuses_and_fixes():
    degraded_html = (
        "<html><head><title>Acme Dental Clinic Kuala Lumpur</title>"
        '<meta name="description" content="Acme Dental Clinic provides gentle, affordable dental '
        'care for families in Kuala Lumpur, from checkups to braces and implants.">'
        "</head><body><h1>One</h1><h1>Two</h1></body></html>"
    )
    routes = dict(_HEALTHY_ROUTES)
    routes["/"] = SafeResponse(200, degraded_html)
    routes["/sitemap.xml"] = SafeResponse(404)
    by = _by_id(_run(routes))
    assert by["sitemap_exists"]["status"] == "fail" and by["sitemap_exists"]["fix"] != ""
    assert by["sitemap_urls"]["status"] == "unknown"
    assert by["sitemap_fresh"]["status"] == "unknown"
    assert by["canonical"]["status"] == "warn" and by["canonical"]["fix"] != ""
    assert by["h1"]["status"] == "warn"
    assert by["viewport"]["status"] == "fail" and by["viewport"]["fix"] != ""


# 4. Homepage timeout → Groups C/D all unknown, A/B unaffected.
def test_homepage_timeout_poisons_only_c_and_d():
    routes = dict(_HEALTHY_ROUTES)
    routes["/"] = httpx.TimeoutException("boom")
    by = _by_id(_run(routes))
    c_d_ids = ["title", "meta_description", "canonical", "open_graph", "h1", "heading_order",
               "viewport", "internal_links", "response_time", "jsonld_present", "jsonld_types"]
    for check_id in c_d_ids:
        assert by[check_id]["status"] == "unknown", check_id
    for check_id in ["robots_exists", "robots_ai_bots", "llms_txt", "llms_full_txt",
                     "sitemap_exists", "sitemap_urls", "sitemap_fresh"]:
        assert by[check_id]["status"] == "pass", check_id


# 5. Sitemap index parses; lastmod 300 days old → warn.
def test_sitemap_index_parses_and_stale_lastmod_warns():
    routes = dict(_HEALTHY_ROUTES)
    routes["/sitemap.xml"] = SafeResponse(200, SITEMAP_INDEX_STALE)
    by = _by_id(_run(routes))
    assert by["sitemap_exists"]["status"] == "pass"
    assert by["sitemap_urls"]["status"] == "pass"
    assert by["sitemap_fresh"]["status"] == "warn"


def test_llms_full_missing_warns_never_fails():
    routes = dict(_HEALTHY_ROUTES)
    routes["/llms-full.txt"] = SafeResponse(404)
    c = _by_id(_run(routes))["llms_full_txt"]
    assert c["status"] == "warn"


def test_http_not_redirecting_warns():
    c = _by_id(_run(_HEALTHY_ROUTES, http_redirects=False))["https"]
    assert c["status"] == "warn"


def test_summarize_counts():
    from app.services.site_audit_service import summarize
    checks = [
        {"id": "a", "label": "", "status": "pass", "detail": "", "fix": ""},
        {"id": "b", "label": "", "status": "pass", "detail": "", "fix": ""},
        {"id": "c", "label": "", "status": "warn", "detail": "", "fix": "x"},
        {"id": "d", "label": "", "status": "fail", "detail": "", "fix": "x"},
        {"id": "e", "label": "", "status": "unknown", "detail": "", "fix": ""},
    ]
    assert summarize(checks) == {"passed": 2, "warned": 1, "failed": 1, "unknown": 1}
