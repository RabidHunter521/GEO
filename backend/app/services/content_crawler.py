# backend/app/services/content_crawler.py
"""Homepage + sitemap website crawler.

Fetches a bounded set of pages (homepage + sitemap URLs, capped) and returns
one CrawlResult that serves both the Claude content analysis (text_corpus) and
the Content Quality assist metrics (word/h1/faq/blog/schema counts).

Not recursive — we only follow sitemap.xml, never page links, so there is no
crawl-trap risk and runtime stays bounded.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.url_safety import is_safe_crawl_url

_TIMEOUT = 10
_MAX_PAGES = 15
_MAX_CORPUS_CHARS = 30_000  # cost guard before any Claude call
_BLOG_PATTERNS = ("/blog/", "/news/", "/articles/", "/article/", "/post/")


def _domain_base(website: str) -> str:
    if "://" not in website:
        website = f"https://{website}"
    parsed = urlparse(website)
    return f"{parsed.scheme}://{parsed.netloc}"


@dataclass
class CrawlResult:
    pages_crawled: int = 0
    text_corpus: str = ""
    word_count: int = 0
    h1_count: int = 0
    faq_count: int = 0
    blog_count: int = 0
    schema_present: bool = False


def discover_pages(website: str) -> list[str]:
    """Return up to _MAX_PAGES same-domain URLs: homepage first, then sitemap URLs."""
    base = _domain_base(website)
    if not is_safe_crawl_url(base):
        return []
    pages: list[str] = [base]
    seen = {base}
    try:
        r = httpx.get(f"{base}/sitemap.xml", timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code == 200:
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text, re.IGNORECASE):
                loc = loc.strip()
                if _domain_base(loc) == base and loc not in seen:
                    seen.add(loc)
                    pages.append(loc)
                if len(pages) >= _MAX_PAGES:
                    break
    except Exception:
        pass
    return pages[:_MAX_PAGES]


def _extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def crawl_site(website: str) -> CrawlResult:
    """Crawl homepage + sitemap pages and aggregate text + structural metrics."""
    pages = discover_pages(website)
    result = CrawlResult()
    result.blog_count = sum(
        1 for p in pages if any(pat in p.lower() for pat in _BLOG_PATTERNS)
    )

    corpus_parts: list[str] = []
    faq_count = 0
    for url in pages:
        if not is_safe_crawl_url(url):
            continue
        try:
            r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
            content_type = r.headers.get("content-type", "").lower()
            if r.status_code != 200 or "html" not in content_type:
                continue
        except Exception:
            continue

        soup = BeautifulSoup(r.text, "lxml")
        result.pages_crawled += 1
        result.h1_count += len(soup.find_all("h1"))

        if soup.find("script", attrs={"type": "application/ld+json"}):
            result.schema_present = True

        if "faq" in url.lower():
            faq_count += 1
        else:
            for heading in soup.find_all(["h1", "h2", "h3"]):
                htext = heading.get_text(strip=True).lower()
                if "faq" in htext or "frequently asked" in htext:
                    faq_count += 1
                    break

        corpus_parts.append(_extract_visible_text(soup))

    result.faq_count = faq_count
    corpus = "\n\n".join(corpus_parts)
    result.word_count = len(corpus.split())
    result.text_corpus = corpus[:_MAX_CORPUS_CHARS]
    return result
