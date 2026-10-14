"""Scan question preview + pack fact checklist.

A packed client is only asked the questions its APPROVED facts can fill, and a
missing fact used to drop its question without a trace. The preview must show
exactly what the next scan asks (same build path) and name what each dropped
question needs; the checklist turns that into a Truth Vault to-do list.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import owner_headers


@pytest.fixture
def api(db):
    from app.core.database import get_db
    from app.main import app

    def fake_get_db():
        yield db

    app.dependency_overrides[get_db] = fake_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _client(db, **overrides):
    from app.models.client import Client

    fields = dict(
        name="Acme Takaful", website="https://acme.example", industry="Insurance",
        buyer_term="takaful operator", city="Kuala Lumpur", country="Malaysia",
        industry_pack="financial_services", industry_subcategory="takaful_operator",
        enabled_platforms=["chatgpt", "perplexity", "gemini"],
    )
    fields.update(overrides)
    client = Client(**fields)
    db.add(client)
    db.commit()
    return client


def _fact(db, client_id, fact_type, key, value, *, status="approved"):
    from app.models.truth_fact import TruthFact, TruthFactVersion

    fact = TruthFact(client_id=client_id, fact_type=fact_type, fact_key=key)
    db.add(fact)
    db.flush()
    approved = status == "approved"
    db.add(TruthFactVersion(
        truth_fact_id=fact.id,
        value_json={"value": value, "display_value": ", ".join(value)},
        status=status,
        effective_from=datetime(2020, 1, 1) if approved else None,
        approved_at=datetime(2020, 1, 1) if approved else None,
        approved_by="admin" if approved else None,
    ))
    db.commit()


def test_preview_names_the_questions_a_missing_fact_drops(db):
    from app.services.question_preview_service import preview

    result = preview(_client(db), db)

    texts = [q["text"] for q in result["questions"]]
    assert "Best takaful plan in Malaysia" in texts
    assert not any("medical card" in t for t in texts)
    skipped = {s["question"]: s["needs"] for s in result["skipped"]}
    assert skipped["Best [product] in [country]"] == [
        "An approved fact: Products offered (e.g. medical card, car insurance, personal loan)"
    ]
    assert result["pack_label"] == "Insurance & Consumer Finance"
    assert result["platform_count"] == 3


def test_approving_the_fact_brings_the_questions_back(db):
    from app.services.question_preview_service import preview

    client = _client(db)
    _fact(db, client.id, "product", "categories", ["medical card"])

    result = preview(client, db)

    texts = [q["text"] for q in result["questions"]]
    assert "Best medical card in Malaysia" in texts
    assert "Best [product] in [country]" not in {s["question"] for s in result["skipped"]}


def test_a_draft_fact_does_not_count(db):
    from app.services.question_preview_service import fact_checklist, preview

    client = _client(db)
    _fact(db, client.id, "product", "categories", ["medical card"], status="draft")

    assert not any("medical card" in q["text"] for q in preview(client, db)["questions"])
    item = next(i for i in fact_checklist(client, db) if i["fact_key"] == "categories")
    assert item["status"] == "draft"


def test_preview_matches_the_scan_build_exactly(db):
    from app.services import pack_query_service
    from app.services.query_builder import build_client_queries
    from app.services.question_preview_service import preview

    client = _client(db, custom_questions=[
        {"text": "Which takaful covers dengue?", "category": "recommendation"},
    ])
    _fact(db, client.id, "product", "categories", ["medical card", "family takaful"])
    pack, locations, facts = pack_query_service.pack_scan_inputs(client, db)
    scanned = [
        q["query_text"]
        for q in build_client_queries(client, [], pack=pack, locations=locations,
                                      approved_facts=facts)
    ]

    result = preview(client, db)

    assert [q["text"] for q in result["questions"]] == scanned
    custom = next(q for q in result["questions"] if q["text"] == "Which takaful covers dengue?")
    assert custom["source"] == "custom"
    assert custom["counts_toward_score"] is True


def test_scored_flag_follows_discovery_categories(db):
    from app.services.question_preview_service import preview

    by_text = {q["text"]: q for q in preview(_client(db), db)["questions"]}
    assert by_text["Best takaful plan in Malaysia"]["counts_toward_score"] is True
    assert by_text["What is Acme Takaful?"]["counts_toward_score"] is False


def test_unpacked_client_previews_the_standard_set(db):
    from app.services.question_preview_service import fact_checklist, preview

    client = _client(db, industry_pack=None, industry_subcategory=None)

    result = preview(client, db)

    assert result["pack_label"] is None
    assert result["skipped"] == []
    assert result["questions"]
    assert {q["source"] for q in result["questions"]} == {"standard"}
    assert fact_checklist(client, db) == []


def test_checklist_lists_what_feeds_questions_and_what_is_risky(db):
    from app.services.question_preview_service import fact_checklist

    client = _client(db)
    _fact(db, client.id, "product", "categories", ["medical card"])

    items = {(i["fact_type"], i["fact_key"]): i for i in fact_checklist(client, db)}

    products = items[("product", "categories")]
    assert products["status"] == "approved"
    assert products["required"] is True
    assert products["question_count"] == 3
    shariah = items[("shariah", "status")]
    assert shariah["risk_sensitive"] is True
    assert shariah["status"] == "missing"
    # Neither required, question-feeding nor risky: optional, not listed.
    assert ("company", "parent") not in items


def test_endpoints_return_preview_and_checklist(api, db):
    client = _client(db)
    headers = owner_headers()

    preview = api.get(f"/api/v1/scans/client/{client.id}/preview", headers=headers)
    checklist = api.get(f"/api/v1/clients/{client.id}/pack-fact-checklist", headers=headers)

    assert preview.status_code == 200, preview.text
    assert any(q["text"] == "Best takaful plan in Malaysia" for q in preview.json()["questions"])
    assert checklist.status_code == 200, checklist.text
    assert any(i["fact_key"] == "categories" for i in checklist.json())


def test_endpoints_404_for_archived_clients_and_need_auth(api, db):
    client = _client(db, archived_at=datetime(2026, 1, 1))
    headers = owner_headers()

    assert api.get(
        f"/api/v1/scans/client/{client.id}/preview", headers=headers
    ).status_code == 404
    assert api.get(
        f"/api/v1/clients/{client.id}/pack-fact-checklist", headers=headers
    ).status_code == 404
    assert api.get(f"/api/v1/scans/client/{client.id}/preview").status_code in (401, 403)
