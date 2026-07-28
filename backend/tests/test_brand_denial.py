"""detect_brand_in_answer — an AI denying knowledge is NOT "Seen by AI".

Every fixture marked REAL is verbatim from scan 5433e572 (throwaway client
cb4708a5, Gemini, 2026-07-28), which scored AI Citability 100.0 because a
plain regex match counted five denials as visibility.
"""
from app.services.brand_detection import detect_brand_in_answer, detect_brand_mention

BRAND = "ZZ Test Prospect TWO DELETE"


# ── the five real answers that caused the bug ──────────────────────────────────

def test_real_denial_does_not_appear_to_be_standard():
    text = ('The phrase "ZZ Test Prospect TWO DELETE" does not appear to be a standard term '
            "or widely recognized concept within the provided search results. However, the "
            "results do offer information related to deleting prospects and testing processes.")
    assert detect_brand_mention(text, BRAND) is True     # the regex still matches
    assert detect_brand_in_answer(text, BRAND) is False  # but it is not visibility


def test_real_denial_placeholder_name():
    text = ('"ZZ Test Prospect TWO DELETE" is a placeholder name, likely used in a testing or '
            "development environment, and is not known for any specific real-world function.")
    assert detect_brand_in_answer(text, BRAND) is False


def test_real_denial_not_widely_recognized_product():
    text = ('The term "ZZ Test Prospect TWO DELETE" does not appear to be a widely recognized '
            "product or service in the automotive or technology sectors based on the search results.")
    assert detect_brand_in_answer(text, BRAND) is False


def test_real_denial_not_standard_concept():
    text = ('The term "ZZ Test Prospect TWO DELETE" does not appear to be a standard or widely '
            "recognized concept in academic research, business reviews, or technology discussions.")
    assert detect_brand_in_answer(text, BRAND) is False


def test_real_hedged_speculation_is_not_visibility():
    """Verbatim shape of the 4th real answer: opens with a hedged guess, then
    speculates conditionally. No denial in the FIRST sentence, which is exactly
    why a first-sentence-only rule was not enough."""
    text = ("ZZ Test Prospect TWO DELETE appears to be related to a system or service that "
            "allows for the deletion of prospect records or workspaces. "
            '* **Data Management:** If "ZZ Test Prospect TWO DELETE" is connected to '
            "Tessitura, it could be involved in managing prospects. "
            'It\'s important to note that the name "ZZ Test Prospect TWO DELETE" suggests '
            "it might be a testing or development instance of a deletion process.")
    assert detect_brand_in_answer(text, BRAND) is False


def test_trailing_speculation_cannot_rescue_an_opening_denial():
    """The regression that made the first attempt at this fix useless.

    A weaker "one clean sentence rescues the answer" rule passed the truncated
    fixtures above and still scored 4 of these 5 real answers as visibility,
    because models deny once and then speculate for several sentences.
    """
    text = ('The term "ZZ Test Prospect TWO DELETE" does not appear to be a widely '
            "recognized product or service. "
            'However, I can provide some information that might be relevant depending on '
            'what "ZZ Test Prospect TWO DELETE" refers to: '
            'If "ZZ Test Prospect TWO DELETE" is an internal project, it likely involves '
            "evaluating or testing something.")
    assert detect_brand_in_answer(text, BRAND) is False


def test_confidently_wrong_but_positive_still_counts():
    """Stance only. A hallucinated but unhedged claim IS a mention — truthfulness
    is handled separately by hallucination_flagged, not here."""
    text = ("Acme Dental is a well-known chain with 40 branches across Malaysia.")
    assert detect_brand_in_answer(text, "Acme Dental") is True


# ── genuine visibility must survive ────────────────────────────────────────────

def test_plain_endorsement_counts():
    assert detect_brand_in_answer(
        "Acme Dental is one of the best-reviewed clinics in Kuala Lumpur.", "Acme Dental") is True


def test_listed_among_recommendations_counts():
    assert detect_brand_in_answer(
        "Top choices include Acme Dental, Bright Smile, and City Dental.", "Acme Dental") is True


def test_one_affirmative_sentence_rescues_a_denial_elsewhere():
    """A denial about one aspect must not erase a real mention in another sentence."""
    text = ("Acme Dental is a well-regarded clinic in Bangsar. "
            "I could not find any information about their weekend opening hours.")
    assert detect_brand_in_answer(text, "Acme Dental") is True


def test_denial_about_a_different_company_is_ignored():
    """The denial only disqualifies sentences that mention THIS brand."""
    text = ("I have no information about Zeta Dental. "
            "Acme Dental, however, is highly rated by patients.")
    assert detect_brand_in_answer(text, "Acme Dental") is True


# ── denial phrasings beyond the observed set ───────────────────────────────────

def test_not_familiar():
    assert detect_brand_in_answer("I'm not familiar with Acme Dental.", "Acme Dental") is False


def test_no_information_about():
    assert detect_brand_in_answer(
        "I have no information about Acme Dental.", "Acme Dental") is False


def test_could_not_find():
    assert detect_brand_in_answer(
        "I couldn't find any results for Acme Dental.", "Acme Dental") is False


def test_does_not_exist():
    assert detect_brand_in_answer(
        "Acme Dental does not exist as far as I can tell.", "Acme Dental") is False


def test_not_aware_of():
    assert detect_brand_in_answer("I am not aware of Acme Dental.", "Acme Dental") is False


def test_may_be_a_typo():
    assert detect_brand_in_answer(
        "Acme Dental may be a typo or a very niche brand.", "Acme Dental") is False


def test_fictional():
    assert detect_brand_in_answer(
        "Acme Dental appears to be a fictional business.", "Acme Dental") is False


# ── the pure matcher must be untouched ─────────────────────────────────────────
# It is still used on CRAWLED PAGE TEXT (provenance_service, authority_service),
# where "not available" is ordinary page copy and must never suppress a match.

def test_pure_matcher_unchanged_by_denial_words():
    page = "Acme Dental — appointments not available online. Call us."
    assert detect_brand_mention(page, "Acme Dental") is True


def test_bullet_list_answer_splits_on_newlines():
    text = ("Here is what I found:\n"
            "* Acme Dental does not appear to be a recognized clinic.\n"
            "* Consider Bright Smile instead.")
    assert detect_brand_in_answer(text, "Acme Dental") is False


def test_empty_and_blank_inputs():
    assert detect_brand_in_answer("", "Acme Dental") is False
    assert detect_brand_in_answer("Some text.", "  ") is False
    assert detect_brand_in_answer(None, "Acme Dental") is False
