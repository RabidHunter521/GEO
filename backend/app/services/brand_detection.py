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
    if not response_text or not brand_name or not brand_name.strip():
        return False
    return _brand_pattern(brand_name).search(response_text) is not None
