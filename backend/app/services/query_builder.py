# backend/app/services/query_builder.py
from app.core.constants import QUERY_TEMPLATES, COMPETITOR_QUERY_TEMPLATES


def build_client_queries(client, competitors: list) -> list[dict]:
    queries = []
    location = f"{client.city}, {client.state}" if client.state else client.city

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

    for template in QUERY_TEMPLATES["recommendation"]:
        queries.append({
            "category": "recommendation",
            "query_text": template.format(industry=client.industry, location=location),
            "competitor_id": None,
        })

    for template in QUERY_TEMPLATES["local"]:
        queries.append({
            "category": "local",
            "query_text": template.format(industry=client.industry, city=client.city),
            "competitor_id": None,
        })

    return queries


def build_competitor_queries(client, competitor) -> list[dict]:
    location = f"{client.city}, {client.state}" if client.state else client.city
    return [
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
        {
            "category": "recommendation",
            "query_text": COMPETITOR_QUERY_TEMPLATES["recommendation"].format(
                industry=client.industry, location=location
            ),
            "competitor_id": competitor.id,
        },
        {
            "category": "local",
            "query_text": COMPETITOR_QUERY_TEMPLATES["local"].format(
                industry=client.industry, city=client.city
            ),
            "competitor_id": competitor.id,
        },
    ]
