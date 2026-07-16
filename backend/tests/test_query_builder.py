from unittest.mock import MagicMock
from app.services.query_builder import build_client_queries, build_competitor_queries


def make_client(name="ACME Corp", industry="consulting", city="Kuala Lumpur", state="WP"):
    client = MagicMock()
    client.name = name
    client.industry = industry
    client.city = city
    client.state = state
    return client


def make_competitor(name="Rival Co"):
    comp = MagicMock()
    comp.id = "comp-id-1"
    comp.name = name
    return comp


def test_client_queries_returns_20_with_five_competitors():
    # 5 templates per category; comparison is capped by competitor count.
    # 5 (brand) + 5 (comparison) + 5 (recommendation) + 5 (local) = 20.
    client = make_client()
    competitors = [make_competitor(f"Rival {i}") for i in range(5)]
    queries = build_client_queries(client, competitors)
    assert len(queries) == 20


def test_client_queries_caps_comparison_to_competitor_count():
    # 2 competitors → only 2 comparison queries: 5 + 2 + 5 + 5 = 17.
    client = make_client()
    competitors = [make_competitor("Rival Co"), make_competitor("Other Co")]
    queries = build_client_queries(client, competitors)
    assert len(queries) == 17


def test_client_queries_returns_15_when_no_competitors():
    # No competitors → no comparison queries: 5 + 0 + 5 + 5 = 15.
    client = make_client()
    queries = build_client_queries(client, [])
    assert len(queries) == 15


def test_client_queries_contain_brand_name():
    client = make_client()
    queries = build_client_queries(client, [])
    brand_queries = [q for q in queries if q["category"] == "brand"]
    assert all("ACME Corp" in q["query_text"] for q in brand_queries)


def test_client_queries_competitor_id_is_none():
    client = make_client()
    competitors = [make_competitor()]
    queries = build_client_queries(client, competitors)
    assert all(q["competitor_id"] is None for q in queries)


def test_queries_collapse_industry_template_word_collision():
    """An industry descriptor ending in a word a template also appends must not
    produce doubled words ('provider providers' shipped to clients once)."""
    client = make_client(industry="health screening company")
    comp = make_competitor()
    # COMPETITOR_QUERY_TEMPLATES recommendation is "Best {industry} company in {location}"
    queries = build_competitor_queries(client, comp)
    rec = next(q for q in queries if q["category"] == "recommendation")
    assert rec["query_text"] == "Best health screening company in Kuala Lumpur, WP"


def test_queries_collapse_singular_plural_collision():
    client = make_client(industry="health screening companies")
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    rec = next(q for q in queries if q["category"] == "recommendation")
    assert rec["query_text"] == "Best health screening companies in Kuala Lumpur, WP"


def test_competitor_queries_returns_4_per_competitor():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    assert len(queries) == 4


def test_competitor_queries_set_competitor_id():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    assert all(q["competitor_id"] == comp.id for q in queries)


def test_competitor_queries_cover_all_categories():
    client = make_client()
    comp = make_competitor()
    queries = build_competitor_queries(client, comp)
    categories = {q["category"] for q in queries}
    assert categories == {"brand", "comparison", "recommendation", "local"}
