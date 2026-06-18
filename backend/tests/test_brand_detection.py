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


def test_short_brand_not_matched_inside_word():
    # "Ace" must not match inside "surface" or "Acme" (boundary-aware).
    assert detect_brand_mention("The surface was clean and Acme shipped it.", "Ace") is False


def test_short_brand_matched_as_whole_word():
    assert detect_brand_mention("We hired Ace for the job.", "Ace") is True


def test_brand_with_trailing_punctuation_matches():
    assert detect_brand_mention("I use Yahoo! every day.", "Yahoo!") is True


def test_brand_with_ampersand_matches():
    assert detect_brand_mention("Call AT&T for service.", "AT&T") is True


def test_blank_brand_returns_false():
    assert detect_brand_mention("Some text.", "   ") is False
