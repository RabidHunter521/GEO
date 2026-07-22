"""Competitor AI-readiness checker.

Checks the client's own site and each tracked competitor's site for the same
technical signals the Technical Foundations / Structured Data GEO Score
dimensions measure (CLAUDE.md §4, §6): llms.txt presence, whether robots.txt
blocks known AI crawlers, and schema.org JSON-LD on the homepage. Results are
informational only — a competitor's readiness never feeds the client's score.

Live, on-demand, not persisted: called from a button click on the
competitors page, not on every page load.
"""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.constants import AI_CRAWLER_BOTS
from app.models.client import Client
from app.models.competitor import Competitor
from app.schemas.ai_readiness import CompetitorAIReadinessResponse, SiteAIReadiness
from app.services.url_safety import is_safe_crawl_url, safe_get
from app.services.verification_crawler import _domain_base, verify_llms_txt

logger = structlog.get_logger()

_TIMEOUT = 10.0


def _parse_robots_groups(text: str) -> dict[str, list[tuple[bool, str]]]:
    """Map each User-agent name to its (is_allow, path) rules, in file order.

    Consecutive User-agent lines share the Allow/Disallow rules that follow
    them, per the robots.txt spec — a rule line closes the current group.
    """
    groups: dict[str, list[tuple[bool, str]]] = {}
    current_agents: list[str] = []
    prev_was_agent_line = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if not prev_was_agent_line:
                current_agents = []
            current_agents.append(value)
            groups.setdefault(value, [])
            prev_was_agent_line = True
        elif field in ("allow", "disallow") and current_agents:
            is_allow = field == "allow"
            for agent in current_agents:
                groups[agent].append((is_allow, value))
            prev_was_agent_line = False
    return groups


def _is_agent_blocked(rules: list[tuple[bool, str]]) -> bool:
    has_root_allow = any(is_allow and path == "/" for is_allow, path in rules)
    has_root_disallow = any(not is_allow and path == "/" for is_allow, path in rules)
    return has_root_disallow and not has_root_allow


def check_robots_ai_bot_access(website: str) -> list[str]:
    """AI bots this site explicitly blocks at the root, per its robots.txt.

    Empty list when there's no file, nothing is blocked, or the fetch fails —
    an unreachable robots.txt is not evidence of blocking.
    """
    try:
        url = f"{_domain_base(website)}/robots.txt"
        if not is_safe_crawl_url(url):
            return []
        r = safe_get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        groups = _parse_robots_groups(r.text)
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
        return blocked
    except Exception:
        return []


def parse_jsonld_scripts(html: str) -> list[dict]:
    """Parsed JSON-LD items in <script type="application/ld+json"> tags.

    Flattens @graph containers, skips malformed JSON and non-dict items.
    Shared by the competitor readiness check and site_audit_service.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        found = data.get("@graph") if isinstance(data, dict) and "@graph" in data else data
        found = found if isinstance(found, list) else [found]
        items.extend(i for i in found if isinstance(i, dict))
    return items


def jsonld_types_from(items: list[dict]) -> list[str]:
    types: list[str] = []
    for item in items:
        t = item.get("@type")
        if isinstance(t, str):
            types.append(t)
        elif isinstance(t, list):
            types.extend(x for x in t if isinstance(x, str))
    return types


def check_homepage_schema(website: str) -> list[str]:
    """@type values found in JSON-LD on the homepage.

    Empty list when there's none, the markup is malformed, or the fetch fails.
    """
    try:
        url = _domain_base(website)
        if not is_safe_crawl_url(url):
            return []
        r = safe_get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        return jsonld_types_from(parse_jsonld_scripts(r.text))
    except Exception:
        return []


def check_site_ai_readiness(name: str, website: str | None) -> SiteAIReadiness:
    if not website:
        return SiteAIReadiness(name=name, website=website, checked=False, has_llms_txt=False)
    return SiteAIReadiness(
        name=name,
        website=website,
        checked=True,
        has_llms_txt=verify_llms_txt(website),
        blocked_ai_bots=check_robots_ai_bot_access(website),
        schema_types=check_homepage_schema(website),
    )


def compute_competitor_ai_readiness(
    client_id: uuid.UUID, db: Session
) -> CompetitorAIReadinessResponse:
    client = db.get(Client, client_id)
    competitors = db.query(Competitor).filter(Competitor.client_id == client_id).all()

    sites: list[tuple[str, str | None]] = [(client.name, client.website)] + [
        (c.name, c.website) for c in competitors
    ]

    def _safe_check(site: tuple[str, str | None]) -> SiteAIReadiness:
        name, website = site
        try:
            return check_site_ai_readiness(name, website)
        except Exception:
            logger.warning("ai_readiness_check_failed", name=name)
            return SiteAIReadiness(name=name, website=website, checked=False, has_llms_txt=False)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(_safe_check, sites))

    return CompetitorAIReadinessResponse(client=results[0], competitors=results[1:])
