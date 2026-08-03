"""Deterministic comparisons between extracted AI claims and approved truth."""
from datetime import timedelta

from app.core.time import utcnow
from app.models.client import Client
from app.models.truth_fact import TruthFact, TruthFactVersion


def _approved_fact(
    db, *, fact_key, value, source_url="https://source.example/fact", status="approved", **version_values
):
    client = Client(name="Klinik A", website="klinik-a.example", industry="dental")
    db.add(client)
    db.flush()
    fact = TruthFact(client_id=client.id, fact_type="business", fact_key=fact_key)
    db.add(fact)
    db.flush()
    version = TruthFactVersion(
        truth_fact_id=fact.id,
        value_json={"value": value, "display_value": str(value)},
        status=status,
        source_url=source_url,
        effective_from=version_values.pop("effective_from", utcnow() - timedelta(days=1)),
        **version_values,
    )
    db.add(version)
    db.commit()
    return fact, version


def _claim(fact_key, value, *, observed_at=None, comparator=None):
    payload = {
        "fact_type": "business",
        "fact_key": fact_key,
        "value": value,
        "answer_quote": f"Klinik A says {value}.",
    }
    if observed_at is not None:
        payload["observed_at"] = observed_at
    if comparator is not None:
        payload["comparator"] = comparator
    return payload


def test_exact_normalized_text_match_does_not_create_a_candidate(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, version = _approved_fact(db, fact_key="official_name", value="Klinik A Dental")

    candidates = compare_claims_to_truth(
        [_claim("official_name", "  klinik a   dental ")], [version]
    )

    assert candidates == []


def test_normalized_phone_and_hours_match_do_not_create_candidates(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, phone = _approved_fact(db, fact_key="phone", value="+65 1234 5678")
    _, hours = _approved_fact(
        db,
        fact_key="hours",
        value={"Monday": ["09:00-17:00"], "Tuesday": ["closed"]},
    )

    candidates = compare_claims_to_truth(
        [
            _claim("phone", "65-1234-5678"),
            _claim("hours", {"tuesday": [], "monday": ["9:00 - 17:00"]}),
        ],
        [phone, hours],
    )

    assert candidates == []


def test_list_claim_is_supported_when_every_claimed_item_is_in_approved_list(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, version = _approved_fact(
        db, fact_key="services", value=["cleanings", "whitening", "implants"]
    )

    candidates = compare_claims_to_truth(
        [_claim("services", ["whitening", "cleanings"])], [version]
    )

    assert candidates == []


def test_normalized_url_and_boolean_match_do_not_create_candidates(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, website = _approved_fact(db, fact_key="website", value="https://Klinik-A.example/")
    _, accepts_walk_ins = _approved_fact(db, fact_key="accepts_walk_ins", value=True)

    candidates = compare_claims_to_truth(
        [
            _claim("website", "klinik-a.example"),
            _claim("accepts_walk_ins", "yes"),
        ],
        [website, accepts_walk_ins],
    )

    assert candidates == []


def test_conflicting_value_returns_unconfirmed_candidate_with_truth_evidence(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    fact, version = _approved_fact(db, fact_key="phone", value="+65 1234 5678")

    candidates = compare_claims_to_truth([_claim("phone", "+65 9999 0000")], [version])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.status == "suggested"
    assert candidate.answer_quote == "Klinik A says +65 9999 0000."
    assert candidate.truth_fact_id == fact.id
    assert candidate.truth_fact_version_id == version.id
    assert candidate.approved_value == "+65 1234 5678"
    assert candidate.source_url == "https://source.example/fact"
    assert candidate.comparator == "phone"


def test_claimed_list_item_missing_from_approved_list_is_a_conflict(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, version = _approved_fact(db, fact_key="services", value=["cleanings", "whitening"])

    candidates = compare_claims_to_truth(
        [_claim("services", ["cleanings", "jaw surgery"])], [version]
    )

    assert len(candidates) == 1
    assert candidates[0].comparator == "list_containment"


def test_fact_outside_the_claim_observation_time_is_excluded(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    observed_at = utcnow() - timedelta(days=3)
    _, version = _approved_fact(
        db,
        fact_key="website",
        value="https://klinik-a.example",
        effective_from=utcnow() - timedelta(days=1),
    )

    candidates = compare_claims_to_truth(
        [_claim("website", "https://old-site.example", observed_at=observed_at)], [version]
    )

    assert candidates == []


def test_draft_versions_are_excluded_from_comparison(db):
    from app.services.truth_comparison_service import compare_claims_to_truth

    _, version = _approved_fact(
        db, fact_key="website", value="https://klinik-a.example", status="draft"
    )

    candidates = compare_claims_to_truth(
        [_claim("website", "https://old-site.example")], [version]
    )

    assert candidates == []
