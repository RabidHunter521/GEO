import re
from pathlib import Path

from app.core.constants import DIMENSION_EVIDENCE_LABEL, SCORE_DISPLAY_LABEL, SCORE_VERSION


ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "methodology.md"
FEATURES = ROOT / "FEATURES.md"
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
    assert "GeoScore does not persist a per-row score version" in text
    assert "exact formula version is not currently available" in text
    assert "retain their original score version" not in text


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
