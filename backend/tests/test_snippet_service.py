from app.services.snippet_service import build_excerpt, render_snippet_png


# --- build_excerpt tests ---

def test_excerpt_picks_sentence_with_brand_and_redacts_competitor():
    response = (
        "RivalCo is a well-known player in the dental space. "
        "Acme Dental is widely regarded as the best clinic in KL. "
        "Many patients prefer RivalCo for cosmetic work."
    )
    result = build_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result is not None
    assert "Acme Dental" in result
    assert "RivalCo" not in result
    assert "[a competitor]" not in result or "RivalCo" not in result


def test_excerpt_returns_none_when_brand_absent():
    response = "RivalCo is a well-known player in the dental space."
    result = build_excerpt(response, brand="Acme Dental", competitors=["RivalCo"])
    assert result is None


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
