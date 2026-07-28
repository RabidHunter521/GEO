# backend/app/services/brand_detection.py
import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _brand_pattern(brand_name: str) -> re.Pattern:
    """Case-insensitive, boundary-aware matcher for a brand name.

    Uses non-word-character lookarounds rather than \\b so brands with leading
    or trailing punctuation ("Yahoo!", "AT&T") still match, while a short brand
    ("Ace") no longer matches inside a larger word ("surface", "Acme").
    Cached because the same handful of brand/competitor names recur across
    every query in a scan.
    """
    return re.compile(rf"(?<!\w){re.escape(brand_name.strip())}(?!\w)", re.IGNORECASE)


def detect_brand_mention(response_text: str, brand_name: str) -> bool:
    """Pure "does this name appear in this text" match.

    Correct for CRAWLED PAGE TEXT (provenance_service, authority_service), where
    the question is only whether a page names the brand. For AI ANSWERS use
    detect_brand_in_answer instead — an answer can name a brand precisely in
    order to say it has never heard of it.
    """
    if not response_text or not brand_name or not brand_name.strip():
        return False
    return _brand_pattern(brand_name).search(response_text) is not None


# Phrases that mean "I don't know this thing". Matched only against sentences
# that already contain the brand, so a denial about something else is ignored.
# Ordered loosely by how often they showed up in real answers.
_DENIAL_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"do(es)?\s*n[o']t\s+(appear|seem)\s+to",
        r"\bis\s+not\s+(a\s+|an\s+|the\s+)?(widely\s+|well[\s-]?)?"
        r"(known|recognis|recogniz|establish|standard)",
        r"\bnot\s+(a\s+|an\s+)?(widely\s+|well[\s-]?)?(known|recognis|recogniz)\w*",
        r"\bnot\s+known\s+for\b",
        r"\b(i|we)\s*('m|'re|\s+am|\s+are)?\s*not\s+(aware|familiar)\b",
        r"\bunfamiliar\s+with\b",
        r"\bno\s+(information|data|record|results?|mention|evidence|listing|details)\b",
        r"\b(could\s*n[o']t|can\s*not|can[o']t|cannot|unable\s+to)\s+(find|locate|identify)\b",
        r"\bdo(es)?\s*n[o']t\s+exist\b",
        r"\b(is|are|appears?\s+to\s+be)\s+(a\s+|an\s+)?(placeholder|fictional|hypothetical|"
        r"made[\s-]?up|fictitious|dummy)\b",
        r"\bmay\s+(not\s+exist|be\s+a\s+typo)\b",
        r"\b(is|might\s+be|could\s+be)\s+(a\s+)?typo\b",
        r"\bno\s+such\s+(company|business|brand|clinic|firm)\b",
        r"\bnever\s+heard\s+of\b",
        # Identity uncertainty: the model is guessing at what the name even
        # denotes. Deliberately narrow — these are about not knowing WHAT the
        # brand is, so they do not fire on ordinary recommendation hedging
        # ("Acme could be a good choice for families").
        r"\bdifficult\s+to\s+(determine|say|pinpoint|tell|ascertain)\b",
        r"\bwithout\s+(further|more|additional)\s+context\b",
        r"\bunclear\s+(what|whether|if)\b",
        r"\bnot\s+sure\s+(what|whether|if)\b",
        r"\b(may|might|could)\s+refer\s+to\b",
        r"\bsuggests?\s+it\s+(might|may|could)\s+be\b",
        r"\bit'?s\s+possible\s+(that\s+)?this\s+is\b",
        r"\bdepending\s+on\s+what\b",
    )
)

# Answers are prose AND markdown bullets, so a "sentence" ends at . ! ? or a
# line break. Splitting matters: it is what keeps a denial about opening hours
# from erasing a genuine mention in the sentence before it.
# The closing-quote class matters: models write `... "Brand Name." Next sentence`
# and a bare (?<=[.!?]) lookbehind sees the quote, not the period, so the two
# sentences stay glued together and a denial leaks into its neighbour.
_SENTENCE_SPLIT = re.compile(r"""(?<=[.!?])["')\]]?\s+|[\r\n]+""")


def detect_brand_in_answer(response_text: str | None, brand_name: str) -> bool:
    """True when an AI answer mentions the brand OTHER than to deny knowing it.

    A plain regex match treats "X does not appear to be a recognized company"
    as visibility, because brand-category queries put the brand name in the
    question and the model echoes it back while denying knowledge. That
    inflated AI Citability — 40% of the GEO score — worst for exactly the
    clients with the least real AI visibility.

    Rule: a denial in ANY sentence naming the brand disqualifies the whole
    answer. The weaker "one clean sentence rescues it" rule was tried first and
    failed on real data — models open with "X does not appear to be a
    recognized company" and then speculate for several sentences ("if X is an
    internal project…", "it could be relevant if X is…"), and that trailing
    guesswork rescued four of five known-bad answers. Speculation about what a
    name might mean is not visibility.

    Only sentences containing the brand are examined, so a denial about
    something else ("I could not find their opening hours") cannot suppress a
    genuine mention.

    Stance only; truthfulness is a separate concern already modelled by
    hallucination_flagged, so a confidently wrong but positive answer still
    counts as seen.
    """
    if not response_text or not brand_name or not brand_name.strip():
        return False
    pattern = _brand_pattern(brand_name)
    if not pattern.search(response_text):
        return False

    for sentence in _SENTENCE_SPLIT.split(response_text):
        if pattern.search(sentence) and any(d.search(sentence) for d in _DENIAL_PATTERNS):
            return False

    # The brand is named and nothing denied it. This also covers the case where
    # odd punctuation defeats the split: falling back to the raw match keeps a
    # real mention rather than silently dropping it.
    return True
