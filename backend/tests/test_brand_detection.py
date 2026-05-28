from app.services.brand_detection import detect_brand_mention


def test_exact_match_returns_true():
    assert detect_brand_mention("ACME Corp is a great company.", "ACME Corp") is True


def test_case_insensitive_match():
    assert detect_brand_mention("acme corp is mentioned here.", "ACME Corp") is True


def test_no_match_returns_false():
    assert detect_brand_mention("Some other company is great.", "ACME Corp") is False


def test_partial_word_not_matched():
    assert detect_brand_mention("ACME is a word.", "ACME Corp") is False


def test_empty_response_returns_false():
    assert detect_brand_mention("", "ACME Corp") is False
