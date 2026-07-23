"""Page citability audit — deterministic AI-readability checks (spec §3).

The 0-100 score is a pure Python sum of earned check points; Claude never
produces the number (same rule as action_center impact). Check details are
plain English (CLAUDE.md §2) — they are shown to the admin and may be
handed to clients alongside the rewrite suggestions.
"""
import re
import statistics
from urllib.parse import urlparse

import structlog
from bs4 import BeautifulSoup

from app.services.url_safety import is_safe_crawl_url, safe_get
from app.services.verification_crawler import _domain_base

logger = structlog.get_logger()

_TIMEOUT = 10.0

_QUESTION_STARTERS = (
    "what", "how", "why", "when", "which", "who", "can", "should", "is", "are", "do", "does",
)
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")
_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:" + "|".join(_MONTHS) + r")\s+\d{4}\b"),
    re.compile(r"\b(?:" + "|".join(_MONTHS) + r")\s+\d{1,2},?\s+\d{4}\b"),
]
_DEFINITION_RE = re.compile(r"\b[A-Z][\w&' -]{0,60}\s+is\s+(?:a|an|the)\s+\w")
_BYLINE_RE = re.compile(r"\b[Bb]y\s+(?:Dr\.?\s+)?[A-Z][a-z]+")


class OffDomainUrlError(ValueError):
    """URL is not on the client's domain (or is unsafe) — nothing was fetched."""


class PageFetchError(RuntimeError):
    """The page could not be fetched or is not an HTML page."""


def validate_audit_url(client_website: str, url: str) -> str | None:
    """Normalized URL when on the client's registrable domain and safe; else None.

    Subdomains of the client domain are allowed (blog.acme.com for acme.com).
    """
    if "://" not in url:
        url = f"https://{url}"
    if not is_safe_crawl_url(url):
        return None
    client_host = urlparse(_domain_base(client_website)).netloc.lower().removeprefix("www.")
    url_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not client_host or not url_host:
        return None
    if url_host == client_host or url_host.endswith("." + client_host):
        return url
    return None


def fetch_page(url: str) -> str:
    """Fetch one HTML page. Raises PageFetchError on any failure —
    an audit with no page behind it is noise and must not persist."""
    try:
        r = safe_get(url, timeout=_TIMEOUT)
    except Exception as exc:
        raise PageFetchError(f"could not fetch {url}") from exc
    content_type = r.headers.get("content-type", "").lower()
    if r.status_code != 200 or ("html" not in content_type and content_type != ""):
        raise PageFetchError(f"{url} returned {r.status_code} ({content_type or 'no content type'})")
    return r.text


def _result(check_id: str, label: str, status: str, detail: str, max_points: int) -> dict:
    earned = max_points if status == "pass" else (max_points // 2 if status == "warn" else 0)
    return {"id": check_id, "label": label, "status": status, "detail": detail, "points": earned}


def _extract(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    # Chrome elements would pollute list/heading counts — drop them before
    # selecting the content root.
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup

    text = main.get_text(" ", strip=True)
    words = text.split()
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    h23 = [h.get_text(" ", strip=True) for h in main.find_all(["h2", "h3"])]
    all_heading_count = len(main.find_all(["h2", "h3", "h4"]))
    faq_headings = [
        h.get_text(" ", strip=True).lower() for h in main.find_all(["h1", "h2", "h3", "h4"])
    ]

    # First content element decides answer_up_front: is there a <p> before any <h2>?
    lead_para: str | None = None
    for el in main.find_all(["p", "h2"]):
        if el.name == "h2":
            break
        lead_para = el.get_text(" ", strip=True)
        if lead_para:
            break

    # Freshness sources beyond visible text: meta dates and <time datetime>.
    meta_date = False
    for meta in soup.find_all("meta"):
        key = (meta.get("property") or meta.get("name") or "").lower()
        if key in ("article:published_time", "article:modified_time", "date",
                   "last-modified", "publish-date", "dc.date"):
            if (meta.get("content") or "").strip():
                meta_date = True
                break
    if not meta_date and soup.find("time", attrs={"datetime": True}):
        meta_date = True

    meta_author = False
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta and (author_meta.get("content") or "").strip():
        meta_author = True
    if not meta_author:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            if '"author"' in (script.string or script.get_text() or ""):
                meta_author = True
                break

    return {
        "text": text,
        "words": words,
        "paragraphs": paragraphs,
        "h23": h23,
        "heading_count": all_heading_count,
        "faq_headings": faq_headings,
        "lead_para": lead_para,
        "tables": len(main.find_all("table")),
        "lists": len(main.find_all(["ul", "ol"])),
        "meta_date": meta_date,
        "meta_author": meta_author,
    }


def _is_question(heading: str) -> bool:
    lowered = heading.lower().strip()
    return lowered.endswith("?") or lowered.split(" ", 1)[0] in _QUESTION_STARTERS


def run_citability_checks(html: str) -> list[dict]:
    """Run the 10 deterministic checks. Always returns exactly 10 dicts."""
    x = _extract(html)
    checks: list[dict] = []

    # 1. answer_up_front (15) — first content paragraph <= 60 words, before any H2.
    lead = x["lead_para"]
    lead_words = len(lead.split()) if lead else 0
    if lead and lead_words <= 60:
        checks.append(_result(
            "answer_up_front", "Answer up front", "pass",
            f"The page opens with a {lead_words}-word summary before the first section.", 15))
    elif lead and lead_words <= 100:
        checks.append(_result(
            "answer_up_front", "Answer up front", "warn",
            f"The opening paragraph is {lead_words} words — trim it to 60 or fewer so AI "
            "assistants can quote it whole.", 15))
    else:
        checks.append(_result(
            "answer_up_front", "Answer up front", "fail",
            "The page doesn't open with a short summary paragraph — AI assistants favour "
            "pages that answer the question in the first 60 words.", 15))

    # 2. question_headings (15) — >= 25% of H2/H3s are question-form.
    if x["h23"]:
        ratio = sum(1 for h in x["h23"] if _is_question(h)) / len(x["h23"])
        if ratio >= 0.25:
            status = "pass"
            detail = f"{ratio:.0%} of section headings are written as questions."
        elif ratio >= 0.10:
            status = "warn"
            detail = (f"Only {ratio:.0%} of section headings are questions — aim for at "
                      "least a quarter, phrased the way a customer would ask.")
        else:
            status = "fail"
            detail = ("Section headings aren't phrased as questions — AI assistants match "
                      "headings to the questions people ask them.")
        checks.append(_result("question_headings", "Question-style headings", status, detail, 15))
    else:
        checks.append(_result(
            "question_headings", "Question-style headings", "fail",
            "The page has no section headings at all.", 15))

    # 3. faq_block (10) — FAQ heading, or >= 3 consecutive question headings.
    has_faq_heading = any("faq" in h or "frequently asked" in h for h in x["faq_headings"])
    consecutive = 0
    max_consecutive = 0
    for h in x["h23"]:
        consecutive = consecutive + 1 if _is_question(h) else 0
        max_consecutive = max(max_consecutive, consecutive)
    if has_faq_heading or max_consecutive >= 3:
        checks.append(_result(
            "faq_block", "FAQ section", "pass", "The page has a question-and-answer section.", 10))
    else:
        checks.append(_result(
            "faq_block", "FAQ section", "fail",
            "No FAQ section found — a short Q&A block is the easiest content for AI "
            "assistants to reuse.", 10))

    # 4. scannable_structure (10) — >= 1 table or >= 2 lists; exactly 1 list warns.
    if x["tables"] >= 1 or x["lists"] >= 2:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "pass",
            f"Found {x['tables']} table(s) and {x['lists']} list(s).", 10))
    elif x["lists"] == 1:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "warn",
            "Only one list on the page — add a comparison table or another list to make "
            "key facts scannable.", 10))
    else:
        checks.append(_result(
            "scannable_structure", "Tables and lists", "fail",
            "No tables or lists — AI assistants extract facts most reliably from "
            "structured elements.", 10))

    # 5. paragraph_length (10) — median paragraph <= 80 words.
    if x["paragraphs"]:
        median = statistics.median(len(p.split()) for p in x["paragraphs"])
        if median <= 80:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "pass",
                f"Median paragraph is {median:.0f} words.", 10))
        elif median <= 120:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "warn",
                f"Median paragraph is {median:.0f} words — break paragraphs up so each "
                "makes one point.", 10))
        else:
            checks.append(_result(
                "paragraph_length", "Paragraph length", "fail",
                f"Median paragraph is {median:.0f} words — walls of text are hard for AI "
                "assistants to quote accurately.", 10))
    else:
        checks.append(_result(
            "paragraph_length", "Paragraph length", "fail",
            "No paragraphs found on the page.", 10))

    # 6. heading_density (10) — >= 1 heading per 300 words.
    word_count = len(x["words"])
    if word_count and x["heading_count"] >= word_count / 300:
        checks.append(_result(
            "heading_density", "Heading coverage", "pass",
            f"{x['heading_count']} headings across {word_count} words.", 10))
    elif word_count and x["heading_count"] >= word_count / 500:
        checks.append(_result(
            "heading_density", "Heading coverage", "warn",
            "Sections run long between headings — aim for a heading roughly every 300 "
            "words.", 10))
    else:
        checks.append(_result(
            "heading_density", "Heading coverage", "fail",
            "Too few headings for the amount of text — AI assistants navigate pages by "
            "their headings.", 10))

    # 7. definitions (5) — an "X is a/an/the …" sentence in the first half.
    first_half = x["text"][: len(x["text"]) // 2]
    if _DEFINITION_RE.search(first_half):
        checks.append(_result(
            "definitions", "Plain definition", "pass",
            "The page defines its subject in plain terms early on.", 5))
    else:
        checks.append(_result(
            "definitions", "Plain definition", "fail",
            'Add an early sentence in the form "X is a …" — definition sentences are '
            "quoted verbatim by AI assistants.", 5))

    # 8. freshness_signal (10) — a parseable date in meta or page text.
    text_date = any(p.search(x["text"]) for p in _DATE_PATTERNS)
    if x["meta_date"] or text_date:
        checks.append(_result(
            "freshness_signal", "Freshness signal", "pass",
            "The page carries a published or updated date.", 10))
    else:
        checks.append(_result(
            "freshness_signal", "Freshness signal", "fail",
            "No visible date — AI assistants prefer content they can tell is current.", 10))

    # 9. author_byline (5) — byline pattern or author meta/JSON-LD.
    if x["meta_author"] or _BYLINE_RE.search(x["text"]):
        checks.append(_result(
            "author_byline", "Author byline", "pass",
            "The page names its author.", 5))
    else:
        checks.append(_result(
            "author_byline", "Author byline", "fail",
            "No author on the page — a named author is a trust signal AI assistants "
            "weigh.", 5))

    # 10. word_count (10) — 300-3000 words; thin or bloated both warn.
    if 300 <= word_count <= 3000:
        checks.append(_result(
            "word_count", "Page length", "pass", f"About {word_count} words.", 10))
    elif 150 <= word_count < 300 or 3000 < word_count <= 5000:
        checks.append(_result(
            "word_count", "Page length", "warn",
            f"About {word_count} words — aim for 300-3,000 words of focused content.", 10))
    else:
        checks.append(_result(
            "word_count", "Page length", "fail",
            f"About {word_count} words — far outside the 300-3,000 word range AI "
            "assistants favour.", 10))

    return checks


def compute_citability_score(checks: list[dict]) -> int:
    """0-100, server-computed. points fields already hold EARNED points."""
    return sum(c["points"] for c in checks)
