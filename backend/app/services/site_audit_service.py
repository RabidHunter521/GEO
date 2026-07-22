"""Site AI-readiness audit — 19 checks across 4 groups (spec 2026-07-11).

Informational only: NO dimension score is derived from these results
(that would bump SCORE_VERSION and is explicitly out of scope). Every
label/detail/fix string is client-facing copy (it lands in the Phase 5
monthly report) — plain English, CLAUDE.md §2 language rules, and all
fix strings are literal constants, never Claude-generated.

A crawl failure must never crash the audit or masquerade as a client
problem: any fetch/parse error yields status "unknown". The audit always
returns exactly 19 checks.
"""
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
import structlog

from app.core.constants import AI_CRAWLER_BOTS
from app.prompts.toolkit import _INDUSTRY_SCHEMA_TYPES
from app.services.ai_readiness_service import (
    _is_agent_blocked,
    _parse_robots_groups,
    jsonld_types_from,
    parse_jsonld_scripts,
)
from app.services.url_safety import is_safe_crawl_url, safe_get
from app.services.verification_crawler import _domain_base

logger = structlog.get_logger()

_TIMEOUT = 10.0
_SITEMAP_FRESH_DAYS = 180
_UNKNOWN_DETAIL = "Could not check — the site didn't respond."
# Schema @types that count as "your business info is present".
_BUSINESS_TYPES = {"Organization", "LocalBusiness"} | {t for _, t in _INDUSTRY_SCHEMA_TYPES}


def _result(check_id: str, label: str, status: str, detail: str, fix: str = "") -> dict:
    return {"id": check_id, "label": label, "status": status, "detail": detail, "fix": fix}


def _unknown(check_id: str, label: str) -> dict:
    return _result(check_id, label, "unknown", _UNKNOWN_DETAIL)


def _fetch(url: str):
    """SafeResponse, or None when the URL is unsafe or the fetch failed."""
    try:
        if not is_safe_crawl_url(url):
            logger.warning("site_audit_unsafe_url", url=url)
            return None
        return safe_get(url, timeout=_TIMEOUT)
    except Exception:
        return None


def _fetch_homepage(base: str):
    """(SafeResponse | None, elapsed_seconds) — simple wall-clock TTLB."""
    start = time.monotonic()
    resp = _fetch(f"{base}/")
    return resp, time.monotonic() - start


def _http_redirects_to_https(base: str) -> bool | None:
    """Does http:// redirect to https://? None = couldn't tell (not evidence).

    Single request, redirects NOT followed — so no SSRF hop risk beyond the
    already-validated host.
    """
    host = urlparse(base).netloc
    url = f"http://{host}/"
    try:
        if not is_safe_crawl_url(url):
            return None
        with httpx.Client(follow_redirects=False, timeout=_TIMEOUT) as client:
            r = client.get(url)
        if r.is_redirect:
            return r.headers.get("location", "").startswith("https://")
        return False  # http serves content without redirecting
    except Exception:
        return None  # port 80 closed etc. — fine for an https-only site


def _same_domain(href: str, base: str) -> bool:
    h = urlparse(href).netloc.lower().removeprefix("www.")
    b = urlparse(base).netloc.lower().removeprefix("www.")
    return h == "" or h == b


def _sitemap_url(base: str, robots) -> str:
    if robots is not None and robots.status_code == 200:
        for line in robots.text.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                candidate = line.partition(":")[2].strip()
                if candidate:
                    return candidate
    return f"{base}/sitemap.xml"


# ── Group A — AI crawl access ────────────────────────────────────────────────

def _group_a(robots, llms, llms_full, homepage, http_redirect) -> list[dict]:
    checks: list[dict] = []

    # 1. robots_exists
    label = "robots.txt file"
    if robots is None:
        checks.append(_unknown("robots_exists", label))
    elif robots.status_code == 200:
        checks.append(_result("robots_exists", label, "pass", "Found robots.txt at /robots.txt."))
    else:
        checks.append(_result(
            "robots_exists", label, "fail",
            f"Your site returned {robots.status_code} for /robots.txt.",
            "Add a robots.txt file at your website root that welcomes AI assistants — "
            "the SeenBy toolkit generates one ready to upload.",
        ))

    # 2. robots_ai_bots — proper per-bot parsing (not the substring check the
    # generated-file verifier uses; that one stays as-is on purpose).
    label = "AI assistants allowed"
    if robots is None:
        checks.append(_unknown("robots_ai_bots", label))
    elif robots.status_code != 200:
        checks.append(_result(
            "robots_ai_bots", label, "pass",
            "No robots.txt found, so no AI assistant is blocked from reading the site.",
        ))
    else:
        groups = _parse_robots_groups(robots.text)
        wildcard_blocked = _is_agent_blocked(groups.get("*", []))
        lower_groups = {agent.lower(): rules for agent, rules in groups.items()}
        blocked = []
        for bot in AI_CRAWLER_BOTS:
            bot_rules = lower_groups.get(bot.lower())
            if bot_rules is not None:
                if _is_agent_blocked(bot_rules):
                    blocked.append(bot)
            elif wildcard_blocked:
                blocked.append(bot)
        if blocked:
            checks.append(_result(
                "robots_ai_bots", label, "fail",
                "robots.txt blocks these AI assistants from reading the site: "
                + ", ".join(blocked) + ".",
                "Update robots.txt to allow these AI assistants — the SeenBy toolkit "
                "generates a ready-to-use file.",
            ))
        else:
            checks.append(_result(
                "robots_ai_bots", label, "pass",
                "All major AI assistants are allowed to read the site.",
            ))

    # 3. llms_txt
    label = "llms.txt file"
    if llms is None:
        checks.append(_unknown("llms_txt", label))
    elif llms.status_code == 200 and llms.text.strip():
        checks.append(_result("llms_txt", label, "pass", "Found llms.txt at /llms.txt."))
    else:
        checks.append(_result(
            "llms_txt", label, "fail",
            "No llms.txt file found — AI assistants have no summary of the business to read.",
            "Generate llms.txt with the SeenBy toolkit and upload it to the website root.",
        ))

    # 4. llms_full_txt — optional file: warn when missing, never fail.
    label = "llms-full.txt file"
    if llms_full is None:
        checks.append(_unknown("llms_full_txt", label))
    elif llms_full.status_code == 200 and llms_full.text.strip():
        checks.append(_result("llms_full_txt", label, "pass", "Found llms-full.txt at /llms-full.txt."))
    else:
        checks.append(_result(
            "llms_full_txt", label, "warn",
            "No llms-full.txt found. It's optional, but gives AI assistants a much "
            "richer picture of the business.",
            "Generate llms-full.txt with the SeenBy toolkit and upload it next to llms.txt.",
        ))

    # 5. https
    label = "Secure connection (HTTPS)"
    if homepage is None:
        checks.append(_unknown("https", label))
    elif homepage.status_code >= 400:
        checks.append(_result(
            "https", label, "fail",
            f"The homepage returned an error ({homepage.status_code}).",
            "Get the homepage loading correctly — AI assistants can't read a page that errors.",
        ))
    elif http_redirect is False:
        checks.append(_result(
            "https", label, "warn",
            "The site works over a secure connection, but the insecure http:// address "
            "doesn't redirect visitors to it.",
            "Ask your web host to redirect http:// to https:// automatically.",
        ))
    else:
        checks.append(_result(
            "https", label, "pass", "The site is served over a secure connection.",
        ))

    return checks


# ── Group B — Sitemap ────────────────────────────────────────────────────────

def _group_b(sitemap, sitemap_url: str) -> list[dict]:
    checks: list[dict] = []
    labels = {
        "sitemap_exists": "Sitemap file",
        "sitemap_urls": "Sitemap lists your pages",
        "sitemap_fresh": "Sitemap freshness",
    }

    root = None
    if sitemap is not None and sitemap.status_code == 200:
        try:
            candidate = ET.fromstring(sitemap.text)
            if candidate.tag.endswith("urlset") or candidate.tag.endswith("sitemapindex"):
                root = candidate
        except ET.ParseError:
            root = None

    # 6. sitemap_exists
    if sitemap is None:
        checks.append(_unknown("sitemap_exists", labels["sitemap_exists"]))
    elif root is not None:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "pass",
            f"Found a valid sitemap at {sitemap_url}.",
        ))
    elif sitemap.status_code == 200:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "fail",
            f"The file at {sitemap_url} isn't a valid sitemap.",
            "Regenerate the sitemap — most website platforms and SEO plugins can "
            "produce a valid sitemap.xml automatically.",
        ))
    else:
        checks.append(_result(
            "sitemap_exists", labels["sitemap_exists"], "fail",
            f"No sitemap found (checked {sitemap_url}).",
            "Publish a sitemap.xml at the website root and list it in robots.txt — "
            "it's how AI systems discover all your pages.",
        ))

    if root is None:
        skip = "Skipped — no valid sitemap to inspect."
        checks.append(_result("sitemap_urls", labels["sitemap_urls"], "unknown", skip))
        checks.append(_result("sitemap_fresh", labels["sitemap_fresh"], "unknown", skip))
        return checks

    # 7. sitemap_urls
    locs = [el for el in root.iter() if el.tag.endswith("loc")]
    if locs:
        checks.append(_result(
            "sitemap_urls", labels["sitemap_urls"], "pass",
            f"The sitemap lists {len(locs)} page{'s' if len(locs) != 1 else ''}.",
        ))
    else:
        checks.append(_result(
            "sitemap_urls", labels["sitemap_urls"], "fail",
            "The sitemap exists but lists no pages.",
            "Regenerate the sitemap so it includes every page you want AI systems to know about.",
        ))

    # 8. sitemap_fresh
    dates = []
    for el in root.iter():
        if el.tag.endswith("lastmod") and el.text:
            raw = el.text.strip()
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(raw[:10])
                except ValueError:
                    continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            dates.append(parsed)
    if not dates:
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "warn",
            "The sitemap has no dates, so AI systems can't tell how fresh your content is.",
            "Add <lastmod> dates to the sitemap — most sitemap generators include them automatically.",
        ))
    elif max(dates) >= datetime.now(UTC) - timedelta(days=_SITEMAP_FRESH_DAYS):
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "pass",
            f"The sitemap was updated within the last {_SITEMAP_FRESH_DAYS} days.",
        ))
    else:
        checks.append(_result(
            "sitemap_fresh", labels["sitemap_fresh"], "warn",
            f"The newest date in the sitemap is more than {_SITEMAP_FRESH_DAYS} days old — "
            "the site looks inactive to AI systems.",
            "Publish or update content, then regenerate the sitemap so its dates reflect it.",
        ))
    return checks


# ── Group C — Homepage content signals ───────────────────────────────────────

_C_LABELS = {
    "title": "Page title",
    "meta_description": "Page description",
    "canonical": "Preferred page address (canonical)",
    "open_graph": "Link preview info (Open Graph)",
    "h1": "Main headline (H1)",
    "heading_order": "Heading structure",
    "viewport": "Mobile-friendly setup",
    "internal_links": "Links between your pages",
    "response_time": "Homepage speed",
}


def _group_c(soup, base: str, elapsed: float) -> list[dict]:
    if soup is None:
        return [_unknown(check_id, label) for check_id, label in _C_LABELS.items()]
    checks: list[dict] = []

    # 9. title — 10–70 chars pass; present but outside range warn; missing fail.
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    if not title:
        checks.append(_result(
            "title", _C_LABELS["title"], "fail",
            "The homepage has no title.",
            "Add a <title> of 10–70 characters that names the business and what it does.",
        ))
    elif 10 <= len(title) <= 70:
        checks.append(_result("title", _C_LABELS["title"], "pass", f'Title found ({len(title)} characters): "{title}".'))
    else:
        checks.append(_result(
            "title", _C_LABELS["title"], "warn",
            f"The title is {len(title)} characters — outside the recommended 10–70 range.",
            "Rewrite the title to 10–70 characters, leading with the business name and main service.",
        ))

    # 10. meta_description — 50–170 chars pass; outside warn; missing fail.
    md_tag = soup.find("meta", attrs={"name": "description"})
    md = (md_tag.get("content") or "").strip() if md_tag else ""
    if not md:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "fail",
            "The homepage has no description tag.",
            "Add a meta description of 50–170 characters summarising what the business "
            "offers and where — AI assistants often quote it directly.",
        ))
    elif 50 <= len(md) <= 170:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "pass",
            f"Description found ({len(md)} characters).",
        ))
    else:
        checks.append(_result(
            "meta_description", _C_LABELS["meta_description"], "warn",
            f"The description is {len(md)} characters — outside the recommended 50–170 range.",
            "Rewrite the meta description to 50–170 characters.",
        ))

    # 11. canonical — missing warn; cross-domain fail; same-domain pass.
    canon = soup.find("link", rel="canonical")
    href = (canon.get("href") or "").strip() if canon else ""
    if not href:
        checks.append(_result(
            "canonical", _C_LABELS["canonical"], "warn",
            "The homepage doesn't declare its preferred address.",
            'Add <link rel="canonical" href="…"> pointing at the homepage\'s own address '
            "so AI systems know which version to trust.",
        ))
    elif _same_domain(href, base):
        checks.append(_result("canonical", _C_LABELS["canonical"], "pass", f"Preferred address declared: {href}."))
    else:
        checks.append(_result(
            "canonical", _C_LABELS["canonical"], "fail",
            f"The preferred address points at a different site: {href}.",
            "Point the canonical link at this site's own homepage address.",
        ))

    # 12. open_graph — og:title + og:description pass; og:image is a detail note only.
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_title and og_desc:
        image_note = " A preview image is set too." if og_image else " No preview image (og:image) is set."
        checks.append(_result(
            "open_graph", _C_LABELS["open_graph"], "pass",
            "Link preview title and description are set." + image_note,
        ))
    else:
        checks.append(_result(
            "open_graph", _C_LABELS["open_graph"], "warn",
            "The homepage is missing link preview tags (og:title / og:description).",
            "Add Open Graph title and description tags so shared links and AI answers "
            "show a clean preview of the business.",
        ))

    # 13. h1 — exactly one pass; none fail; more than one warn.
    h1s = soup.find_all("h1")
    if len(h1s) == 1:
        checks.append(_result("h1", _C_LABELS["h1"], "pass", "The homepage has exactly one main headline."))
    elif len(h1s) == 0:
        checks.append(_result(
            "h1", _C_LABELS["h1"], "fail",
            "The homepage has no main headline (H1).",
            "Add one H1 that states the business name and what it does.",
        ))
    else:
        checks.append(_result(
            "h1", _C_LABELS["h1"], "warn",
            f"The homepage has {len(h1s)} main headlines — there should be exactly one.",
            "Keep one H1 and turn the others into H2 subheadings.",
        ))

    # 14. heading_order — no skipped levels in the first 20 headings; warn only.
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])[:20]
    prev_level = 0
    skipped = False
    for h in headings:
        level = int(h.name[1])
        if prev_level and level > prev_level + 1:
            skipped = True
            break
        prev_level = level
    if skipped:
        checks.append(_result(
            "heading_order", _C_LABELS["heading_order"], "warn",
            "Headings skip levels (for example jumping from H2 straight to H4), which "
            "makes the page structure harder for AI systems to follow.",
            "Keep headings in order: H1, then H2 sections, then H3 details within them.",
        ))
    else:
        checks.append(_result(
            "heading_order", _C_LABELS["heading_order"], "pass",
            "Headings are in a clean, logical order.",
        ))

    # 15. viewport — mobile-friendliness proxy.
    if soup.find("meta", attrs={"name": "viewport"}):
        checks.append(_result("viewport", _C_LABELS["viewport"], "pass", "The page is set up for mobile screens."))
    else:
        checks.append(_result(
            "viewport", _C_LABELS["viewport"], "fail",
            "The page has no mobile viewport tag — it may render poorly on phones.",
            'Add <meta name="viewport" content="width=device-width, initial-scale=1"> '
            "to the page head.",
        ))

    # 16. internal_links — ≥10 same-domain links pass; below warn.
    count = 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if _same_domain(href, base):
            count += 1
    if count >= 10:
        checks.append(_result(
            "internal_links", _C_LABELS["internal_links"], "pass",
            f"The homepage links to {count} of your own pages.",
        ))
    else:
        checks.append(_result(
            "internal_links", _C_LABELS["internal_links"], "warn",
            f"The homepage links to only {count} of your own pages.",
            "Link from the homepage to your key service pages so AI systems can find them.",
        ))

    # 17. response_time — wall-clock on the homepage fetch. <2s pass, 2–5s warn, >5s fail.
    if elapsed < 2:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "pass",
            f"The homepage responded in {elapsed:.1f}s.",
        ))
    elif elapsed <= 5:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "warn",
            f"The homepage took {elapsed:.1f}s to respond — slower than the 2s target.",
            "Ask your web host or developer about speeding the site up (caching, image "
            "compression, better hosting).",
        ))
    else:
        checks.append(_result(
            "response_time", _C_LABELS["response_time"], "fail",
            f"The homepage took {elapsed:.1f}s to respond.",
            "A page this slow gets skipped. Ask your web host or developer about caching "
            "and hosting upgrades.",
        ))
    return checks


# ── Group D — Structured data ────────────────────────────────────────────────

_D_LABELS = {
    "jsonld_present": "Structured data present",
    "jsonld_types": "Business info in structured data",
}


def _group_d(soup, html: str | None) -> list[dict]:
    if soup is None or html is None:
        return [_unknown(check_id, label) for check_id, label in _D_LABELS.items()]
    checks: list[dict] = []
    items = parse_jsonld_scripts(html)
    types = jsonld_types_from(items)

    # 18. jsonld_present
    if items:
        checks.append(_result(
            "jsonld_present", _D_LABELS["jsonld_present"], "pass",
            f"Found {len(items)} structured data entr{'ies' if len(items) != 1 else 'y'} on the homepage.",
        ))
    else:
        checks.append(_result(
            "jsonld_present", _D_LABELS["jsonld_present"], "fail",
            "No structured data found on the homepage.",
            "Add schema.org structured data — the SeenBy toolkit generates a schema.json "
            "file with everything AI systems need.",
        ))

    # 19. jsonld_types — pass when a business-type entry is present.
    if types and set(types) & _BUSINESS_TYPES:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "pass",
            "Business details are present in structured data. Types found: " + ", ".join(sorted(set(types))) + ".",
        ))
    elif types:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "warn",
            "Structured data exists but doesn't describe the business itself. Types found: "
            + ", ".join(sorted(set(types))) + ".",
            "Add an Organization or LocalBusiness entry — the SeenBy toolkit's schema.json includes one.",
        ))
    else:
        checks.append(_result(
            "jsonld_types", _D_LABELS["jsonld_types"], "warn",
            "No business details in structured data, so AI systems can't confirm who you are.",
            "Add an Organization or LocalBusiness entry — the SeenBy toolkit's schema.json includes one.",
        ))
    return checks


# ── Entry points ─────────────────────────────────────────────────────────────

def run_site_audit(website: str) -> list[dict]:
    """Run all 19 checks against a website. Always returns exactly 19 dicts."""
    from bs4 import BeautifulSoup  # local import keeps module import light

    base = _domain_base(website)
    with ThreadPoolExecutor(max_workers=5) as pool:
        robots_f = pool.submit(_fetch, f"{base}/robots.txt")
        llms_f = pool.submit(_fetch, f"{base}/llms.txt")
        llms_full_f = pool.submit(_fetch, f"{base}/llms-full.txt")
        home_f = pool.submit(_fetch_homepage, base)
        http_f = pool.submit(_http_redirects_to_https, base)
        robots = robots_f.result()
        llms = llms_f.result()
        llms_full = llms_full_f.result()
        homepage, elapsed = home_f.result()
        http_redirect = http_f.result()

    # Sitemap URL can come from robots.txt, so this fetch happens after.
    sm_url = _sitemap_url(base, robots)
    sitemap = _fetch(sm_url)

    homepage_ok = homepage is not None and homepage.status_code == 200
    soup = BeautifulSoup(homepage.text, "html.parser") if homepage_ok else None
    html = homepage.text if homepage_ok else None

    checks: list[dict] = []
    checks += _group_a(robots, llms, llms_full, homepage, http_redirect)
    checks += _group_b(sitemap, sm_url)
    checks += _group_c(soup, base, elapsed)
    checks += _group_d(soup, html)
    return checks


def summarize(checks: list[dict]) -> dict:
    return {
        "passed": sum(1 for c in checks if c["status"] == "pass"),
        "warned": sum(1 for c in checks if c["status"] == "warn"),
        "failed": sum(1 for c in checks if c["status"] == "fail"),
        "unknown": sum(1 for c in checks if c["status"] == "unknown"),
    }
