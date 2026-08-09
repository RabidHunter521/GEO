# backend/app/services/page_readability.py
"""Readable-content gate for crawled pages.

HTTP 200 is not proof that a page can be read. Login walls, client-rendered
shells and challenge interstitials all answer 200 with a large HTML document
whose visible text is a word or two — facebook.com/<brand> ships ~465 KB of
markup and the single word "<Brand>".

That produced a real false positive: `authority_service.verify_asset` matched
the brand name in that one word, flipped the asset to "verified", and published
"Facebook page — now verified" to the client's progress view. The page was a
login wall.

The gate is deliberately size-aware rather than a bare word floor. A
legitimately thin page — a sparse contact page, a one-line directory listing —
is SMALL and must still be read; the pathology is a LARGE document that yields
no text. Both conditions must hold before a page is rejected, so the thin-page
false positive cannot happen.

Measured against live pages 2026-08-09:

    facebook.com/<brand>     465 KB       1 word   → rejected
    google.com/maps/place    213 KB       2 words  → rejected
    youtube.com/@<brand>    1454 KB      27 words  → rejected (footer chrome only)
    instagram.com/<brand>    710 KB     103 words  → read (real profile text)
    linkedin.com/company     360 KB    1910 words  → read
    a real client homepage   801 KB    1395 words  → read

Callers pass the text they already extracted, so nothing is parsed twice.
"""

#: Below this many visible words a large document is treated as unreadable.
#: 40 sits ~2.5x above YouTube's chrome-only yield (27) and well below the
#: smallest genuine page measured (103), so both sides have margin.
MIN_VISIBLE_WORDS = 40

#: Only documents at least this large are eligible for rejection. Real thin
#: pages are orders of magnitude smaller than the shells this catches.
LARGE_DOCUMENT_BYTES = 50_000


def looks_unreadable(html: str, visible_text: str) -> bool:
    """True when substantial markup yielded almost no readable text.

    `html` is the raw response body, `visible_text` the text the caller already
    extracted from it (scripts/styles stripped).
    """
    if len(html) < LARGE_DOCUMENT_BYTES:
        return False
    return len(visible_text.split()) < MIN_VISIBLE_WORDS
