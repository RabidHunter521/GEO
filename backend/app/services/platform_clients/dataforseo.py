# backend/app/services/platform_clients/dataforseo.py
"""Shared HTTP adapter for Google's AI surfaces, bought from DataForSEO.

Google has no official API for AI Overviews or AI Mode, so both come from a
SERP-data vendor. Everything vendor-specific lives here — endpoints, auth,
status codes, the answer item's shape — so swapping vendors touches this
file and nothing in the scan engine.

No retries here: `query_with_retry` owns retry-once and the circuit breaker.
"""
import re

import httpx

from app.core.constants import (
    GOOGLE_SERP_DEVICE,
    GOOGLE_SERP_LANGUAGE_CODE,
    GOOGLE_SERP_LOCATION_CODE,
)
from app.services.platform_clients.base import (
    PLATFORM_QUERY_TIMEOUT_SECONDS,
    PlatformResult,
    collect_citations,
)

API_BASE = "https://api.dataforseo.com/v3/serp/google"
AI_OVERVIEW_ENDPOINT = "organic/live/advanced"
AI_MODE_ENDPOINT = "ai_mode/live/advanced"

_OK = 20000
# Vendor codes the circuit breaker must treat as quota / rate trouble, mapped
# onto the HTTP statuses `circuit_breaker.is_rate_or_payment_error` reads.
_PAYMENT_CODES = {40200, 40210}
_RATE_CODES = {40202, 40203, 40205, 40206, 40209}

# Images carry nothing a buyer reads and no brand signal; links keep their text.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BLANK_RUNS = re.compile(r"\n{3,}")


class DataForSEOError(RuntimeError):
    """A task-level failure. `status_code` is set to 402 / 429 for quota and
    rate errors so the provider breaker counts them like any other platform."""

    def __init__(self, code: int | None, message: str):
        super().__init__(f"DataForSEO {code}: {message}")
        self.vendor_code = code
        if code in _PAYMENT_CODES:
            self.status_code = 402
        elif code in _RATE_CODES:
            self.status_code = 429


def post_task(login: str, password: str, endpoint: str, keyword: str, **extra) -> dict:
    """POST one live task and return its `result[0]` (raises on any failure)."""
    payload = [{
        "keyword": keyword,
        "location_code": GOOGLE_SERP_LOCATION_CODE,
        "language_code": GOOGLE_SERP_LANGUAGE_CODE,
        "device": GOOGLE_SERP_DEVICE,
        **extra,
    }]
    response = httpx.post(
        f"{API_BASE}/{endpoint}",
        auth=(login, password),
        json=payload,
        timeout=PLATFORM_QUERY_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if body.get("status_code") != _OK:
        raise DataForSEOError(body.get("status_code"), str(body.get("status_message")))
    tasks = body.get("tasks") or []
    if not tasks:
        raise DataForSEOError(None, "response carried no task")
    task = tasks[0]
    if task.get("status_code") != _OK:
        raise DataForSEOError(task.get("status_code"), str(task.get("status_message")))
    results = task.get("result") or []
    if not results or not isinstance(results[0], dict):
        raise DataForSEOError(task.get("status_code"), "task returned no result")
    return results[0]


def find_ai_answer(result: dict) -> dict | None:
    """The `ai_overview` item of a result, or None when Google showed none."""
    for item in result.get("items") or []:
        if isinstance(item, dict) and item.get("type") == "ai_overview":
            return item
    return None


def answer_text(item: dict) -> str:
    """Readable answer text from the item's markdown (images dropped, link
    targets dropped, link text kept)."""
    markdown = item.get("markdown") or ""
    text = _MD_IMAGE.sub("", markdown)
    text = _MD_LINK.sub(r"\1", text)
    return _BLANK_RUNS.sub("\n\n", text).strip()


def answer_citations(item: dict):
    """The item's `references`, in order, as SourceCitations."""
    return collect_citations(
        (ref.get("url"), ref.get("title"), None)
        for ref in item.get("references") or []
        if isinstance(ref, dict)
    )


def to_result(item: dict | None, model: str, *, answer_always_shown: bool) -> PlatformResult:
    """Map an answer item onto the scan engine's PlatformResult.

    Every call is billed per request whatever it returns, so search_requests
    is 1 even when Google showed no answer. A surface that always answers
    (AI Mode) leaves answer_shown None, like every LLM platform; only a
    surface that may show nothing (AI Overviews) records True / False.
    """
    if item is None:
        if answer_always_shown:
            raise DataForSEOError(None, "no AI answer in the result")
        return PlatformResult(
            text="", model=model, input_tokens=0, output_tokens=0,
            search_requests=1, answer_shown=False,
        )
    text = answer_text(item)
    if not text:
        # An item with no readable text is not an answer a buyer saw.
        if answer_always_shown:
            raise DataForSEOError(None, "AI answer had no text")
        return PlatformResult(
            text="", model=model, input_tokens=0, output_tokens=0,
            search_requests=1, answer_shown=False,
        )
    return PlatformResult(
        text=text, model=model, input_tokens=0, output_tokens=0,
        citations=answer_citations(item), search_requests=1,
        answer_shown=None if answer_always_shown else True,
    )
