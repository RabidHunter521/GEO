from app.services.snippet_service import build_excerpt, build_loss_excerpt, render_snippet_png


# --- build_excerpt tests ---

def test_excerpt_picks_sentence_with_brand_and_redacts_competitor():
    # The brand sentence itself names a competitor, so redaction is exercised.
    response = (
        "There are several clinics in KL. "
        "Acme Dental is widely regarded as better than RivalCo for implants. "
        "Many patients also consider OtherDent."
    )
    result = build_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result is not None
    assert "Acme Dental" in result
    # The chosen sentence mentioned RivalCo; redaction must have replaced it.
    assert "RivalCo" not in result
    assert "[a competitor]" in result


def test_excerpt_returns_none_when_brand_absent():
    response = "RivalCo is a well-known player in the dental space."
    result = build_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result is None


def test_excerpt_brand_must_match_whole_word_not_substring():
    """A short brand must not match inside a larger word (Ace ≠ Acme)."""
    response = "Acme Dental is the best clinic in town."
    assert build_excerpt(response, brand="Ace", competitors=[]) is None


def test_excerpt_truncates_long_sentence():
    long_sentence = "Acme Dental " + ("x " * 200)
    result = build_excerpt(long_sentence, brand="Acme Dental", competitors=[])
    assert result is not None
    assert len(result) <= 280
    assert result.endswith("…")


def test_excerpt_empty_response_returns_none():
    result = build_excerpt("", brand="Acme Dental", competitors=[])
    assert result is None


def test_excerpt_redacts_multiple_competitors():
    response = "Acme Dental beats RivalCo and OtherDent in every category."
    result = build_excerpt(response, brand="Acme Dental", competitors=["RivalCo", "OtherDent"])
    assert result is not None
    assert "RivalCo" not in result
    assert "OtherDent" not in result
    assert result.count("[a competitor]") == 2


def test_excerpt_no_competitors_returns_verbatim_sentence():
    response = "Acme Dental is the top clinic in KL."
    result = build_excerpt(response, brand="Acme Dental", competitors=[])
    assert result == "Acme Dental is the top clinic in KL."


# --- build_loss_excerpt tests ---

def test_build_loss_excerpt_redacts_competitor_when_brand_absent():
    response = "For dental care in KL, RivalCo is the most recommended clinic. They have great reviews."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result == "For dental care in KL, [a competitor] is the most recommended clinic."


def test_build_loss_excerpt_none_when_brand_present():
    response = "Acme Dental and RivalCo are both strong choices in KL."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_none_when_no_competitor_named():
    response = "There are many good dental clinics in KL to choose from."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_none_when_no_competitors_configured():
    response = "RivalCo is the most recommended clinic in KL."
    assert build_loss_excerpt(response, brand="Acme Dental", competitors=[]) is None


def test_build_loss_excerpt_empty_text():
    assert build_loss_excerpt("", brand="Acme Dental", competitors=["RivalCo"]) is None


def test_build_loss_excerpt_truncates_long_sentence():
    long_sentence = "RivalCo " + "is widely recommended " * 40 + "in KL."
    result = build_loss_excerpt(long_sentence, brand="Acme Dental", competitors=["RivalCo"])
    assert result is not None and len(result) <= 280 and result.endswith("…")


# --- render_snippet_png tests ---

def test_render_snippet_png_returns_png_bytes():
    png = render_snippet_png(
        platform_label="ChatGPT",
        brand="Acme Dental",
        excerpt="Acme Dental is widely regarded as the best clinic in KL.",
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


def test_render_snippet_png_different_platforms():
    for label in ["Perplexity", "Gemini", "Claude"]:
        png = render_snippet_png(
            platform_label=label,
            brand="Test Brand",
            excerpt="Test Brand is a leading company.",
        )
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


# --- build_loss_excerpt with redact parameter tests ---

def test_build_loss_excerpt_names_competitor_when_redact_false():
    response = "For dental care in KL, RivalCo is the most recommended clinic. They have great reviews."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"], redact=False)
    assert result == "For dental care in KL, RivalCo is the most recommended clinic."


def test_build_loss_excerpt_default_still_redacts():
    response = "For dental care in KL, RivalCo is the most recommended clinic."
    result = build_loss_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result == "For dental care in KL, [a competitor] is the most recommended clinic."
