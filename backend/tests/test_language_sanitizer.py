# backend/tests/test_language_sanitizer.py
"""Unit tests for the shared §2 vocabulary sanitizer."""

from app.services.language_sanitizer import sanitize_text, sanitize_bullets


# ── sanitize_text ──────────────────────────────────────────────────────────────

def test_sanitize_text_replaces_mentioned_and_citation_rate():
    result = sanitize_text("we were mentioned; citation rate high")
    assert "mentioned" not in result.lower()
    assert "citation rate" not in result.lower()
    assert "seen by ai" in result.lower()
    assert "visibility frequency" in result.lower()


def test_sanitize_text_replaces_not_mentioned_before_mentioned():
    """'not mentioned' must become 'not seen by AI', not 'not seen by AI' → 'not seen by AI' again."""
    result = sanitize_text("The brand was not mentioned anywhere")
    assert "not seen by AI" in result
    assert "mentioned" not in result.lower()


def test_sanitize_text_replaces_uncited():
    result = sanitize_text("The brand is uncited in most queries")
    assert "uncited" not in result.lower()
    assert "not seen by AI" in result


def test_sanitize_text_replaces_cited():
    result = sanitize_text("The brand is cited frequently")
    assert "cited" not in result.lower()
    assert "seen by AI" in result


def test_sanitize_text_replaces_ranking_position():
    result = sanitize_text("Their ranking position is 3rd")
    assert "ranking position" not in result.lower()
    assert "AI Search Ranking" in result


def test_sanitize_text_replaces_visibility_gap():
    result = sanitize_text("There is a visibility gap versus rivals")
    assert "visibility gap" not in result.lower()
    assert "Your competitors are winning here" in result


def test_sanitize_text_replaces_first_mentioned():
    result = sanitize_text("They were first mentioned in Q2")
    assert "first mentioned" not in result.lower()
    assert "first seen by AI" in result


def test_sanitize_text_is_case_insensitive():
    result = sanitize_text("Brand was MENTIONED and CITED in many queries")
    assert "mentioned" not in result.lower()
    assert "cited" not in result.lower()


def test_sanitize_text_handles_none():
    assert sanitize_text(None) == ""


def test_sanitize_text_handles_empty_string():
    assert sanitize_text("") == ""


def test_sanitize_text_does_not_raise_on_arbitrary_input():
    # Should never raise regardless of input
    result = sanitize_text("No forbidden terms here — just normal text.")
    assert "No forbidden terms here" in result


# ── sanitize_bullets ──────────────────────────────────────────────────────────

def test_sanitize_bullets_replaces_forbidden_terms():
    out = sanitize_bullets([
        "Brand was mentioned in 3 articles",
        "Strong citation rate on Reddit",
    ])
    joined = " ".join(out).lower()
    assert "mentioned" not in joined
    assert "citation rate" not in joined
    assert "seen by ai" in joined
    assert "visibility frequency" in joined


def test_sanitize_bullets_drops_empty_after_strip():
    out = sanitize_bullets(["  ", "Valid bullet", ""])
    assert out == ["Valid bullet"]


def test_sanitize_bullets_returns_empty_list_for_empty_input():
    assert sanitize_bullets([]) == []
