import re
from pathlib import Path

from app.core.constants import DIMENSION_EVIDENCE_LABEL, SCORE_DISPLAY_LABEL, SCORE_VERSION


ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "methodology.md"
FEATURES = ROOT / "docs" / "FEATURES.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"

REQUIRED_SECTIONS = [
    "Measurement layers",
    "Query coverage",
    "Sampling and variability",
    "Technical and publisher files",
    "Attribution and estimates",
    "Versioning",
    "Limitations",
]


def test_methodology_documents_current_score_contract():
    text = METHODOLOGY.read_text(encoding="utf-8")
    assert SCORE_VERSION in text
    assert SCORE_DISPLAY_LABEL in text
    assert re.findall(r"^## (.+)$", text, flags=re.MULTILINE) == REQUIRED_SECTIONS
    assert "AI Presence" in text
    assert "Accuracy and Reputation" in text
    assert "Growth Readiness" in text
    assert "Business Impact" in text
    assert "AI citability (40%)" in text
    assert "brand authority (20%)" in text
    assert "content quality (20%)" in text
    assert "verified robots.txt AI-crawler access (10%)" in text
    assert "verified structured data (10%)" in text


def test_methodology_discloses_optional_files_and_uncertainty():
    text = METHODOLOGY.read_text(encoding="utf-8").lower()
    assert "llms.txt" in text
    assert "optional" in text
    assert "does not independently increase" in text
    assert "answers can vary" in text
    assert "estimated" in text


def test_methodology_documents_manual_review_and_truthful_versioning_limits():
    text = METHODOLOGY.read_text(encoding="utf-8")
    assert DIMENSION_EVIDENCE_LABEL in text
    assert "v1.4.0 labels newly computed Growth Readiness" in text
    # New rows carry their version (migration 1a3fd284901c)...
    assert "carries the version of the method that produced it" in text
    # ...and the doc must stay honest that legacy rows do NOT, rather than
    # quietly implying the whole history is attributable.
    assert "carry no version" in text
    assert "cannot be established" in text
    assert "not comparable" in text
    # Guards against the two flattering claims: that old rows have a version,
    # or that history was rewritten to the current formula.
    assert "retain their original score version" not in text
    assert "are not recomputed" in text


def test_methodology_promises_the_disclosure_the_product_actually_makes():
    """The doc claims a version mismatch is disclosed to the client. That claim
    is only true while the digest and report gates exist - pin them together."""
    from app.services.scoring_service import scores_comparable

    text = METHODOLOGY.read_text(encoding="utf-8")
    assert "does not present the difference as a change" in text
    assert scores_comparable("v1.4.0", "v1.3.0") is False
    assert scores_comparable("v1.4.0", None) is False
    assert scores_comparable("v1.4.0", "v1.4.0") is True


def test_methodology_is_published_to_clients_not_just_the_repo():
    """A methodology that ships to nobody is not a disclosure. The client-facing
    payload must carry the same weights the doc states."""
    from app.core.constants import SCORE_WEIGHTS
    from app.services.methodology_service import build_methodology

    published = build_methodology()
    assert published["score_version"] == SCORE_VERSION
    by_key = {d["key"]: d["weight_percent"] for d in published["dimensions"]}
    assert by_key == {k: round(v * 100) for k, v in SCORE_WEIGHTS.items()}
    assert sum(by_key.values()) == 100


def test_feature_documentation_matches_current_scan_coverage_and_contract():
    features = FEATURES.read_text(encoding="utf-8")
    architecture = ARCHITECTURE.read_text(encoding="utf-8")

    assert "Up to 20 queries per enabled platform per scan" in features
    assert "five brand queries, up to five comparison queries, five recommendation queries, and five local queries" in features
    assert "fewer competitors" in features
    assert DIMENSION_EVIDENCE_LABEL in features
    assert "Growth Readiness (`overall_score` in the current API)" in features
    assert "[measurement methodology](docs/methodology.md)" in features
    assert "[the methodology](methodology.md)" in architecture
