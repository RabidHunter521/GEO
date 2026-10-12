# backend/app/services/brand_detection.py
import re
from functools import lru_cache
from typing import Iterable


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


# Tail for the identity-uncertainty patterns below: within the same clause the
# hedge must be about what the name IS ("...what X refers to", "...whether X is
# a real company", "...what X is."), never about which option is better.
_IDENTITY_TAIL = (
    r"[^.!?\n]{0,80}?\b(refers?\s+to|referring\s+to|you\s+mean|is\s+meant|means|denotes|"
    r"stands\s+for|exists?|is\s+(a|an)\s+(real|actual|specific|particular|legitimate)\b|"
    r"(is|does)\s*(?=[.,;:!?)\n]|$))"
)

# Phrases that mean "I don't know this thing". Matched only against sentences
# that already contain the brand, so a denial about something else is ignored.
# Ordered loosely by how often they showed up in real answers.
_DENIAL_PATTERNS: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        # "is not widely known OUTSIDE Shah Alam" is a scope qualifier on a
        # known business, not a denial -- hence the lookaheads on the next two.
        # The possessive \w*+ stops "recognised outside" backtracking to
        # "recognise" + "d" and slipping past the lookahead.
        r"do(es)?\s*n[o']t\s+(appear|seem)\s+to",
        r"\bis\s+not\s+(a\s+|an\s+|the\s+)?(widely\s+|well[\s-]?)?"
        r"(known|recognis|recogniz|establish|standard)\w*+(?!\s+(outside|beyond)\b)",
        r"\bnot\s+(a\s+|an\s+)?(widely\s+|well[\s-]?)?(known|recognis|recogniz)\w*+"
        r"(?!\s+(outside|beyond)\b)",
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
        # Real answers that deny knowledge without any of the phrasings above.
        r"\bdo(es)?\s*n[o']t\s+have\s+(any\s+)?(information|data|details|records?)\b",
        r"\bdo(es)?\s*n[o']t\s+appear\s+(in|on)\s+(the\s+|any\s+)?"
        r"(sources?|search\s+results|results|listings?|records?|directories)\b",
        r"\bnot\s+a\s+(business|company|brand|clinic|firm)\s+(i|we)\s+(can|could)\s+find\b",
        # Malay: "tidak dapat mencari/menemui", "tiada maklumat", "tidak mengenali".
        r"\btidak\s+dapat\s+(mencari|menemui|mengenal\s*pasti)\b",
        r"\btiada\s+maklumat\b",
        r"\btidak\s+mengenali\b",
        # Identity uncertainty: the model is guessing at what the name even
        # denotes. Each one is pinned to the IDENTITY of the thing ("what X
        # refers to", "whether X is a real company"), not to a judgement about
        # it. The unpinned versions ("difficult to say", "unclear whether",
        # "depending on what", "may refer to") fired on the ordinary hedging of
        # comparison and shortlist answers about well-known brands -- "choose
        # Curlec or Billplz depending on what you need", "unclear whether
        # Curlec supports BNPL" -- and zeroed genuine mentions.
        r"\b(difficult|hard|impossible)\s+to\s+(determine|say|pinpoint|tell|ascertain|know)\s+"
        r"(exactly\s+)?(what|who|which)\b" + _IDENTITY_TAIL,
        r"\bwithout\s+(further|more|additional)\s+context\b" + _IDENTITY_TAIL,
        r"\b(unclear|not\s+(entirely\s+)?sure|uncertain)\s+(exactly\s+)?(what|who|whether|if)\b"
        + _IDENTITY_TAIL,
        r"\b(may|might|could)\s+refer\s+to\s+(several|multiple|many|various|different|"
        r"a\s+(number|variety|range)\s+of|one\s+of|either|any|something)\b",
        r"\bsuggests?\s+it\s+(might|may|could)\s+be\b",
        r"\bit'?s\s+possible\s+(that\s+)?this\s+is\b",
        r"\bdepending\s+on\s+what\b" + _IDENTITY_TAIL,
    )
)

# Answers are prose AND markdown bullets, so a "sentence" ends at . ! ? or a
# line break. Splitting matters: it is what keeps a denial about opening hours
# from erasing a genuine mention in the sentence before it.
# The closing-quote class matters: models write `... "Brand Name." Next sentence`
# and a bare (?<=[.!?]) lookbehind sees the quote, not the period, so the two
# sentences stay glued together and a denial leaks into its neighbour.
_SENTENCE_SPLIT = re.compile(r"""(?<=[.!?])["')\]]?\s+|[\r\n]+""")


def brand_names(entity) -> tuple[str, ...]:
    """Every name an AI answer may use for a client or competitor: its name
    plus any admin-entered aliases ("Razorpay Curlec" for "Curlec", or a
    rebranded competitor's former name). Blank entries are dropped."""
    names = [getattr(entity, "name", None), *(getattr(entity, "brand_aliases", None) or ())]
    return tuple(dict.fromkeys(n.strip() for n in names if isinstance(n, str) and n.strip()))


def name_in_text(response_text: str | None, names: Iterable[str]) -> str | None:
    """The first of `names` the text actually uses, or None. Lets a step that
    needs ONE name (position extraction) look for the one the answer used."""
    if not response_text:
        return None
    for name in names:
        if isinstance(name, str) and name.strip() and _brand_pattern(name).search(response_text):
            return name
    return None


def detect_brand_in_answer(
    response_text: str | None, brand_name: str, aliases: Iterable[str] = ()
) -> bool:
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

    `aliases` are other names for the same brand. Any of them counts as the
    brand, and a denial in a sentence naming any of them disqualifies the
    answer exactly as one naming `brand_name` would.
    """
    if not response_text or not brand_name or not brand_name.strip():
        return False
    patterns = [
        _brand_pattern(name)
        for name in dict.fromkeys([brand_name, *aliases])
        if isinstance(name, str) and name.strip()
    ]
    if not any(p.search(response_text) for p in patterns):
        return False

    for sentence in _SENTENCE_SPLIT.split(response_text):
        if any(p.search(sentence) for p in patterns) and any(
            d.search(sentence) for d in _DENIAL_PATTERNS
        ):
            return False

    # The brand is named and nothing denied it. This also covers the case where
    # odd punctuation defeats the split: falling back to the raw match keeps a
    # real mention rather than silently dropping it.
    return True
