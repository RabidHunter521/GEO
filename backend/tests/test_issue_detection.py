"""Client-facing issue groups must never assert something we did not observe.

The bug these tests lock down: the reviewed-dimension pools
(_BRAND_AUTHORITY_ISSUES / _CONTENT_QUALITY_ISSUES) were emitted purely from a
score threshold, so an unassessed client — whose score is the model default of
0, not a measurement — was shown specific factual claims about their business
("Sparse customer reviews or testimonials", "Minimal media coverage") under a
badge reading "Based on public evidence · Reviewed by SeenBy". Nothing had been
researched and nobody had reviewed it.
"""
import pytest

from app.core.constants import DIMENSION_EVIDENCE_LABEL
from app.core.time import utcnow
from app.models.client import Client
from app.models.dimension_assessment import DimensionAssessment
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.services.issue_detection_service import detect_client_issues


def _client(db, **overrides) -> Client:
    c = Client(
        name="Acme Dental",
        website="https://acme.example",
        industry="dental clinic",
        city="Kuala Lumpur",
    )
    for k, v in overrides.items():
        setattr(c, k, v)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _score(db, client_id, **overrides) -> GeoScore:
    # A real completed scan: geo_scores.scan_id is a FK, and detect_client_issues
    # looks the scan up. No query results, so the AI Visibility branch stays
    # silent and these tests only exercise the dimension pools.
    scan = Scan(client_id=client_id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    row = GeoScore(
        client_id=client_id,
        scan_id=scan.id,
        ai_citability=40.0,
        brand_authority=0.0,
        content_quality=0.0,
        technical_foundations=0.0,
        structured_data=0.0,
        overall_score=16.0,
        score_version="v1.4.0",
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return row


def _accept(db, client_id, dimension, score=45):
    db.add(DimensionAssessment(
        client_id=client_id,
        dimension=dimension,
        suggested_score=score,
        final_score=score,
        evidence_bullets=["Listed on two directories", "No press coverage found"],
        status="accepted",
    ))
    db.commit()


def _group(groups, dimension):
    return next((g for g in groups if g["dimension"] == dimension), None)


# ── the core bug ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dimension", ["brand_authority", "content_quality"])
def test_unassessed_dimension_emits_no_issues(db, dimension):
    """A default-0 score means 'not assessed yet', not 'scored badly'."""
    client = _client(db)
    _score(db, client.id)

    groups = detect_client_issues(client, db)

    assert _group(groups, dimension) is None


@pytest.mark.parametrize("dimension", ["brand_authority", "content_quality"])
def test_assessed_dimension_emits_issues_with_evidence_label(db, dimension):
    client = _client(db)
    _score(db, client.id, **{dimension: 45.0})
    _accept(db, client.id, dimension)

    group = _group(detect_client_issues(client, db), dimension)

    assert group is not None
    assert group["issues"], "an assessed, low-scoring dimension should report findings"
    assert group["evidence_label"] == DIMENSION_EVIDENCE_LABEL


def test_suggested_but_unreviewed_assessment_emits_no_issues(db):
    """Claude suggesting a score is not a human having reviewed it."""
    client = _client(db)
    _score(db, client.id, brand_authority=45.0)
    db.add(DimensionAssessment(
        client_id=client.id,
        dimension="brand_authority",
        suggested_score=45,
        evidence_bullets=["Found on one directory"],
        status="suggested",
    ))
    db.commit()

    assert _group(detect_client_issues(client, db), "brand_authority") is None


# ── unmeasured claims trimmed from the auto-verified pools ───────────────────

def test_technical_issues_limited_to_the_verified_fact(db):
    """robots.txt verification is the only technical thing we actually check."""
    client = _client(db, technical_foundations_verified=False)
    _score(db, client.id)

    group = _group(detect_client_issues(client, db), "technical_foundations")

    assert group is not None
    assert group["issues"] == [
        "Website is not yet verified as accessible to AI crawlers"
    ]
    # Never claim page speed / crawl / meta problems we never measured.
    joined = " ".join(group["issues"]).lower()
    assert "page speed" not in joined
    assert "meta information" not in joined
    assert "indexing" not in joined


def test_structured_data_issues_limited_to_the_verified_fact(db):
    client = _client(db, structured_data_verified=False)
    _score(db, client.id)

    group = _group(detect_client_issues(client, db), "structured_data")

    assert group is not None
    joined = " ".join(group["issues"]).lower()
    assert "no verified schema markup" in joined
    # Never name specific schema types we never looked for.
    assert "faq" not in joined
    assert "organization" not in joined


def test_verified_dimensions_emit_no_issues(db):
    client = _client(
        db, technical_foundations_verified=True, structured_data_verified=True
    )
    _score(db, client.id, technical_foundations=100.0, structured_data=100.0)

    groups = detect_client_issues(client, db)

    assert _group(groups, "technical_foundations") is None
    assert _group(groups, "structured_data") is None


# ── the badge must never appear on a dimension nobody reviewed ───────────────

def test_measured_dimensions_carry_no_evidence_label(db):
    client = _client(db)
    _score(db, client.id)

    for group in detect_client_issues(client, db):
        if group["dimension"] in ("brand_authority", "content_quality"):
            continue
        assert group["evidence_label"] is None, (
            f"{group['dimension']} is measured, not reviewed — it must not claim "
            "human review"
        )


def test_no_score_yet_returns_nothing(db):
    client = _client(db)
    assert detect_client_issues(client, db) == []
