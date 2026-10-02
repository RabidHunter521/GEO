"""Google AI Overviews + AI Mode adapters (DataForSEO), Task 1."""
import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from app.services import circuit_breaker
from app.services.platform_clients import PlatformNotConfiguredError, get_platform_client
from app.services.platform_clients.dataforseo import DataForSEOError
from app.services.platform_clients.google_ai_mode import GoogleAIModeClient
from app.services.platform_clients.google_ai_overview import GoogleAIOverviewClient

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "dataforseo"


def _response(name: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json.loads((_FIXTURES / f"{name}.json").read_text())
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture(autouse=True)
def _closed_breaker():
    with patch("app.services.platform_clients.base.circuit_breaker") as mcb:
        mcb.is_open.return_value = False
        mcb.is_rate_or_payment_error.side_effect = circuit_breaker.is_rate_or_payment_error
        yield mcb


def _post(name: str):
    return patch("app.services.platform_clients.dataforseo.httpx.post", return_value=_response(name))


def test_overview_text_is_readable_and_sources_are_its_references():
    with _post("aio_present"):
        result = GoogleAIOverviewClient("login", "pw").query("best dental clinic in KL")

    assert result.answer_shown is True
    assert "Acme Dental" in result.text
    assert "Bright Smile in Mont Kiara" in result.text  # link text kept, target dropped
    assert "gstatic" not in result.text and "![" not in result.text
    assert "\n\n\n" not in result.text
    # utm + fragment stripped, duplicate collapsed, answer order kept
    assert [c.url for c in result.citations] == [
        "https://klguide.example/best-dentists", "https://brightsmile.my/",
    ]
    assert result.citations[0].title == "10 Best Dentists in KL"
    assert (result.model, result.input_tokens, result.output_tokens, result.search_requests) == (
        "dataforseo-google-aio", 0, 0, 1,
    )


def test_overview_request_targets_malaysia_english_mobile_and_loads_async_overviews():
    with _post("aio_present") as post:
        GoogleAIOverviewClient("login", "pw").query("best dental clinic in KL")

    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]
    assert url.endswith("/serp/google/organic/live/advanced")
    assert post.call_args.kwargs["auth"] == ("login", "pw")
    assert body == [{
        "keyword": "best dental clinic in KL",
        "location_code": 2458,
        "language_code": "en",
        "device": "mobile",
        "load_async_ai_overview": True,
    }]


def test_search_without_an_overview_is_an_observation_not_an_error():
    with _post("aio_absent"):
        result = GoogleAIOverviewClient("login", "pw").query("acme dental bangsar opening hours")

    assert result.answer_shown is False
    assert result.text == ""
    assert result.citations == ()
    assert result.search_requests == 1  # still billed


def test_ai_mode_answer_parses():
    with _post("ai_mode") as post:
        result = GoogleAIModeClient("login", "pw").query("best dental clinic in KL")

    assert post.call_args.args[0].endswith("/serp/google/ai_mode/live/advanced")
    assert "load_async_ai_overview" not in post.call_args.kwargs["json"][0]
    assert result.answer_shown is True
    assert result.text.startswith("For dental care in KL, **Bright Smile**")
    assert [c.url for c in result.citations] == ["https://brightsmile.my/"]
    assert result.model == "dataforseo-google-ai-mode"


def test_ai_mode_without_an_answer_fails_and_is_retried_once():
    with _post("ai_mode_empty") as post, pytest.raises(DataForSEOError):
        GoogleAIModeClient("login", "pw").query("x")
    assert post.call_count == 2


def test_insufficient_funds_counts_toward_the_breaker(_closed_breaker):
    with _post("task_payment_error"), pytest.raises(DataForSEOError) as err:
        GoogleAIOverviewClient("login", "pw").query("x")

    assert err.value.status_code == 402
    assert _closed_breaker.record_failure.call_count == 2


def test_missing_credentials_mark_the_platform_not_configured():
    with patch("app.services.platform_clients.settings") as s:
        s.DATAFORSEO_LOGIN = ""
        s.DATAFORSEO_PASSWORD = ""
        for platform in ("google_aio", "google_ai_mode"):
            with pytest.raises(PlatformNotConfiguredError):
                get_platform_client(platform)


def test_google_platforms_are_reported_but_not_scored():
    from app.core.constants import PLATFORM_LABELS, SCAN_PLATFORMS, SCORED_PLATFORMS

    assert {"google_aio", "google_ai_mode"} <= set(SCAN_PLATFORMS)
    assert PLATFORM_LABELS["google_aio"] == "Google AI Overviews"
    assert PLATFORM_LABELS["google_ai_mode"] == "Google AI Mode"
    assert set(SCORED_PLATFORMS) == {"chatgpt", "perplexity", "gemini", "claude"}


def test_google_requests_are_priced_per_request():
    from app.services.cost_tracker import _compute_cost

    assert float(_compute_cost("dataforseo-google-aio", 0, 0, 1)) == pytest.approx(0.0026)
    assert float(_compute_cost("dataforseo-google-ai-mode", 0, 0, 1)) == pytest.approx(0.004)


# ── Task 2: the scan records whether an answer was shown ───────────────────

def _run_one(platform_client, tracked_samples=()):
    import uuid

    from app.services.scan_service import _run_platform_queries

    scan = MagicMock(id=uuid.uuid4())
    client = MagicMock(id=uuid.uuid4())
    client.name = "Acme Dental"
    queries = [{"query_text": "best dental clinic in KL", "category": "recommendation"}]
    with patch("app.services.scan_service.time.sleep"), \
            patch("app.services.scan_service.extract_position", return_value=2) as pos:
        rows, usages = _run_platform_queries(
            platform_client.platform, platform_client, scan, client, [], [], queries,
            list(tracked_samples),
        )
    return rows, usages, pos


def _sample():
    import uuid
    return {"query_text": "best dental clinic in KL", "category": "recommendation",
            "tracked_query_id": uuid.uuid4(), "sample_index": 1, "prompt_version": "v1"}


def test_scan_stores_a_missing_overview_as_not_seen_with_no_quote():
    with _post("aio_absent"):
        rows, usages, pos = _run_one(GoogleAIOverviewClient("login", "pw"))

    [row] = rows
    assert row.platform == "google_aio"
    assert row.answer_shown is False
    assert row.brand_detected is False
    assert row.response_text == ""
    assert row.sources_captured is True and row.sources == []
    assert row.recommendation_position is None
    pos.assert_not_called()
    assert usages[0].search_requests == 1  # the request is still cost-logged


def test_scan_stores_a_shown_overview_with_its_sources():
    with _post("aio_present"):
        rows, _, _ = _run_one(GoogleAIOverviewClient("login", "pw"))

    [row] = rows
    assert row.answer_shown is True and row.brand_detected is True
    assert [s.domain for s in row.sources] == ["klguide.example", "brightsmile.my"]


def test_google_surfaces_skip_repeat_samples():
    with _post("aio_present") as post:
        rows, _, _ = _run_one(GoogleAIOverviewClient("login", "pw"), [_sample()])

    assert len(rows) == 1 and post.call_count == 1


def test_llm_platform_rows_leave_answer_shown_unset():
    from app.services.platform_clients.base import PlatformResult

    llm = MagicMock(platform="chatgpt")
    llm.query.return_value = PlatformResult(
        text="Acme Dental is great.", model="gpt-5-mini", input_tokens=1, output_tokens=1,
    )
    rows, _, _ = _run_one(llm, [_sample()])

    assert len(rows) == 2  # repeat samples still run for LLM platforms
    assert all(r.answer_shown is None for r in rows)
