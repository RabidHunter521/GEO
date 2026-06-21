import uuid
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.core import constants


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
