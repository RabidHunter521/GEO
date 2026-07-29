from pathlib import Path

from app.core.constants import SCORE_DISPLAY_LABEL, SCORE_VERSION


ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "methodology.md"


def test_methodology_documents_current_score_contract():
    text = METHODOLOGY.read_text(encoding="utf-8")
    assert SCORE_VERSION in text
    assert SCORE_DISPLAY_LABEL in text
    assert "AI Presence" in text
    assert "Accuracy and Reputation" in text
    assert "Business Impact" in text


def test_methodology_discloses_optional_files_and_uncertainty():
    text = METHODOLOGY.read_text(encoding="utf-8").lower()
    assert "llms.txt" in text
    assert "optional" in text
    assert "does not independently increase" in text
    assert "answers can vary" in text
    assert "estimated" in text
