"""The readable-content gate: large document + no visible text = unreadable.

Sizes and word counts here mirror what live pages actually returned when the
gate was designed (see the module docstring in page_readability.py), so a
future threshold change has to justify itself against real measurements.
"""

from app.services.page_readability import (
    LARGE_DOCUMENT_BYTES,
    MIN_VISIBLE_WORDS,
    looks_unreadable,
)


def _big(html_bytes: int) -> str:
    """A document of the given size whose bulk is markup, not text."""
    return "<div class='x'></div>" * (html_bytes // 21)


def test_large_document_with_one_word_is_unreadable():
    """facebook.com/<brand>: ~465 KB of markup, visible text is just the brand."""
    assert looks_unreadable(_big(465_000), "Nike") is True


def test_large_document_with_only_chrome_is_unreadable():
    """youtube.com/@<brand>: 1.4 MB, 27 words of footer boilerplate."""
    chrome = " ".join(f"word{i}" for i in range(27))
    assert looks_unreadable(_big(1_454_000), chrome) is True


def test_large_document_with_real_content_is_readable():
    """instagram.com/<brand>: 710 KB but a genuine 103-word profile."""
    body = " ".join(f"word{i}" for i in range(103))
    assert looks_unreadable(_big(710_000), body) is False


def test_small_thin_page_is_readable():
    """A sparse contact page is SMALL — it must never trip the gate."""
    html = (
        "<html><body><h1>Acme Dental Clinic</h1>"
        "<p>Call us at +60 3-1234 5678. 12 Jalan Ampang, Kuala Lumpur.</p>"
        "</body></html>"
    )
    text = "Acme Dental Clinic Call us at +60 3-1234 5678. 12 Jalan Ampang, Kuala Lumpur."
    assert len(html) < LARGE_DOCUMENT_BYTES
    assert len(text.split()) < MIN_VISIBLE_WORDS  # thin, but small — still read
    assert looks_unreadable(html, text) is False


def test_empty_page_is_readable_when_small():
    """An empty small response is a different failure; the caller's own
    name/status checks already handle it honestly."""
    assert looks_unreadable("", "") is False


def test_boundary_word_count_is_readable():
    """At exactly the floor the page is kept — the gate rejects below it."""
    body = " ".join(f"word{i}" for i in range(MIN_VISIBLE_WORDS))
    assert looks_unreadable(_big(200_000), body) is False
