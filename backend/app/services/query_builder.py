# backend/app/services/query_builder.py
from app.core.constants import QUERY_TEMPLATES, COMPETITOR_QUERY_TEMPLATES

# Version of the scan visibility-query templates. Bump when the templates in
# QUERY_TEMPLATES / COMPETITOR_QUERY_TEMPLATES change, so cost rows for scan
# platforms (service "scan_<platform>") are tied to the query set that produced
# them — the same provenance the Claude prompts get via the prompt registry.
SCAN_QUERY_VERSION = "v2"


def _location(client) -> str | None:
    """Human "City, State" string from whatever location fields are set.

    Falls back city → state → country so a client with only a country still
    gets a usable location. None when no location is known at all — callers
    then skip the location/local queries rather than emit "... in None".
    """
    if client.city and client.state:
        return f"{client.city}, {client.state}"
    return client.city or client.state or client.country or None


def _locality(client) -> str | None:
    """Most specific single place name for the {city}-style local queries."""
    return client.city or client.state or client.country or None


def build_client_queries(client, competitors: list) -> list[dict]:
    queries = []
    location = _location(client)
    locality = _locality(client)

    for template in QUERY_TEMPLATES["brand"]:
        queries.append({
            "category": "brand",
            "query_text": template.format(brand=client.name),
            "competitor_id": None,
        })

    for i, template in enumerate(QUERY_TEMPLATES["comparison"]):
        if i < len(competitors):
            queries.append({
                "category": "comparison",
                "query_text": template.format(brand=client.name, competitor=competitors[i].name),
                "competitor_id": None,
            })

    # Location/local queries are skipped entirely when no location is known, so
    # a client with no city never gets "Best <industry> in None" garbage queries.
    if location:
        for template in QUERY_TEMPLATES["recommendation"]:
            queries.append({
                "category": "recommendation",
                "query_text": template.format(industry=client.industry, location=location),
                "competitor_id": None,
            })

    if locality:
        for template in QUERY_TEMPLATES["local"]:
            queries.append({
                "category": "local",
                "query_text": template.format(industry=client.industry, city=locality),
                "competitor_id": None,
            })

    return queries


def build_competitor_queries(client, competitor) -> list[dict]:
    location = _location(client)
    locality = _locality(client)
    queries = [
        {
            "category": "brand",
            "query_text": COMPETITOR_QUERY_TEMPLATES["brand"].format(competitor=competitor.name),
            "competitor_id": competitor.id,
        },
        {
            "category": "comparison",
            "query_text": COMPETITOR_QUERY_TEMPLATES["comparison"].format(
                competitor=competitor.name, brand=client.name
            ),
            "competitor_id": competitor.id,
        },
    ]
    if location:
        queries.append({
            "category": "recommendation",
            "query_text": COMPETITOR_QUERY_TEMPLATES["recommendation"].format(
                industry=client.industry, location=location
            ),
            "competitor_id": competitor.id,
        })
    if locality:
        queries.append({
            "category": "local",
            "query_text": COMPETITOR_QUERY_TEMPLATES["local"].format(
                industry=client.industry, city=locality
            ),
            "competitor_id": competitor.id,
        })
    return queries
