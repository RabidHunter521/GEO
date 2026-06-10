from urllib.parse import urlparse

import httpx

_TIMEOUT = 10


def _domain_base(website: str) -> str:
    if "://" not in website:
        website = f"https://{website}"
    parsed = urlparse(website)
    return f"{parsed.scheme}://{parsed.netloc}"


def verify_llms_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/llms.txt"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        return r.status_code == 200 and len(r.text.strip()) > 0
    except Exception:
        return False


def verify_schema_json(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/schema.json"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return False
        r.json()
        return True
    except Exception:
        return False


def verify_robots_txt(website: str) -> bool:
    try:
        url = f"{_domain_base(website)}/robots.txt"
        r = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return False
        return "gptbot" in r.text.lower()
    except Exception:
        return False


def verify_all(website: str) -> dict[str, bool]:
    return {
        "llms_verified": verify_llms_txt(website),
        "schema_verified": verify_schema_json(website),
        "robots_verified": verify_robots_txt(website),
    }
