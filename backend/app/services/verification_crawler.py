from urllib.parse import urlparse

from app.services.url_safety import is_safe_crawl_url, safe_get

_TIMEOUT = 10


def _domain_base(website: str) -> str:
    if "://" not in website:
        website = f"https://{website}"
    parsed = urlparse(website)
    return f"{parsed.scheme}://{parsed.netloc}"


def verify_llms_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/llms.txt"
        if not is_safe_crawl_url(url):
            return False
        r = safe_get(url, timeout=_TIMEOUT)
        return r.status_code == 200 and len(r.text.strip()) > 0
    except Exception:
        return False


def verify_schema_json(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/schema.json"
        if not is_safe_crawl_url(url):
            return False
        r = safe_get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return False
        r.json()
        return True
    except Exception:
        return False


def verify_robots_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/robots.txt"
        if not is_safe_crawl_url(url):
            return False
        r = safe_get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return False
        return "gptbot" in r.text.lower()
    except Exception:
        return False


def verify_llms_full_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/llms-full.txt"
        if not is_safe_crawl_url(url):
            return False
        r = safe_get(url, timeout=_TIMEOUT)
        return r.status_code == 200 and len(r.text.strip()) > 0
    except Exception:
        return False


def verify_all(website: str) -> dict[str, bool]:
    return {
        "llms_verified": verify_llms_txt(website),
        "schema_verified": verify_schema_json(website),
        "robots_verified": verify_robots_txt(website),
        # Informational only — never drives a dimension score (spec §6).
        "llms_full_verified": verify_llms_full_txt(website),
    }
