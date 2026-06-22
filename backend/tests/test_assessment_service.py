import uuid
from unittest.mock import patch, MagicMock

from app.core import constants
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.prompts import assessment as assessment_prompts
from app.services import assessment_service


def _client(db):
    c = Client(id=uuid.uuid4(), name="Acme", website="https://acme.my", industry="dentist")
    db.add(c)
    db.commit()
    return c


def test_dimension_assessment_row_roundtrips(db):
    c = _client(db)
    row = DimensionAssessment(
        client_id=c.id,
        dimension="brand_authority",
        suggested_score=58,
        evidence_bullets=["Active on Reddit in 3 relevant communities"],
        raw_narrative="full reasoning",
        status="suggested",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.id is not None
    assert row.final_score is None
    assert row.evidence_bullets == ["Active on Reddit in 3 relevant communities"]
    assert row.status == "suggested"
    assert row.generated_at is not None


def test_assessment_constants_present():
    assert constants.SCORE_VERSION == "v1.2.0"
    assert constants.ASSESSABLE_DIMENSIONS == ("brand_authority", "content_quality")
    assert constants.ASSESSMENT_STATUSES == ("suggested", "accepted", "adjusted")
    assert constants.DIMENSION_EVIDENCE_LABEL == "Based on public evidence · Reviewed by SeenBy"


def test_prompt_includes_business_and_json_contract(db):
    c = _client(db)
    p = assessment_prompts.build_assessment_prompt(c, "brand_authority")
    assert "Acme" in p and "dentist" in p
    assert '"score"' in p and '"bullets"' in p and '"narrative"' in p
    # language rules surfaced to the model
    assert "seen by ai" in p.lower()


def test_prompt_rejects_unknown_dimension(db):
    c = _client(db)
    try:
        assessment_prompts.build_assessment_prompt(c, "made_up")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_sanitize_bullets_replaces_forbidden_terms():
    out = assessment_service.sanitize_bullets([
        "Brand was mentioned in 3 articles",
        "Strong citation rate on Reddit",
    ])
    joined = " ".join(out).lower()
    assert "mentioned" not in joined
    assert "citation rate" not in joined
    assert "seen by ai" in joined


def _fake_response(text):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage = MagicMock(input_tokens=10, output_tokens=20)
    return resp


def test_generate_assessment_persists_suggested_row(db):
    c = _client(db)
    payload = '{"score": 58, "bullets": ["Listed on Google with 40 reviews"], "narrative": "ok"}'
    with patch.object(assessment_service, "anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response(payload)
        row = assessment_service.generate_assessment(c, "brand_authority", db)
    assert row is not None
    assert row.status == "suggested"
    assert row.suggested_score == 58
    assert row.final_score is None
    assert row.evidence_bullets == ["Listed on Google with 40 reviews"]
    assert row.raw_narrative == "ok"


def test_generate_assessment_returns_none_on_bad_json(db):
    c = _client(db)
    with patch.object(assessment_service, "anthropic_client") as mk:
        mk.return_value.messages.create.return_value = _fake_response("not json")
        row = assessment_service.generate_assessment(c, "brand_authority", db)
    assert row is None
    assert db.query(DimensionAssessment).count() == 0


def test_generate_assessment_returns_none_on_unknown_dimension(db):
    """KeyError from unknown dimension should be caught and return None."""
    c = _client(db)
    row = assessment_service.generate_assessment(c, "made_up_dimension", db)
    assert row is None


def _suggested_row(db, client, dimension="brand_authority", score=58):
    row = DimensionAssessment(
        client_id=client.id, dimension=dimension, suggested_score=score,
        evidence_bullets=["Listed on Google with 40 reviews", "Active subreddit presence"],
        raw_narrative="n", status="suggested",
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_accept_writes_through_to_client(db):
    c = _client(db)
    _suggested_row(db, c, score=58)
    row = assessment_service.accept_assessment(c, "brand_authority", None, db)
    db.refresh(c)
    assert row.status == "accepted"
    assert row.final_score == 58
    assert row.reviewed_at is not None
    assert c.brand_authority_score == 58
    assert "Listed on Google with 40 reviews" in (c.brand_authority_evidence or "")


def test_accept_with_adjusted_score_marks_adjusted(db):
    c = _client(db)
    _suggested_row(db, c, score=58)
    row = assessment_service.accept_assessment(c, "brand_authority", 65, db)
    db.refresh(c)
    assert row.status == "adjusted"
    assert row.final_score == 65
    assert c.brand_authority_score == 65


def test_accept_without_suggestion_returns_none(db):
    c = _client(db)
    assert assessment_service.accept_assessment(c, "content_quality", None, db) is None
