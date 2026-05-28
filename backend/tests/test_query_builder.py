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


def test_client_queries_returns_8_when_two_competitors():
    client = make_client()
    competitors = [make_competitor("Rival Co"), make_competitor("Other Co")]
    queries = build_client_queries(client, competitors)
    assert len(queries) == 8


def test_client_queries_returns_6_when_no_competitors():
    client = make_client()
    queries = build_client_queries(client, [])
    assert len(queries) == 6


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
