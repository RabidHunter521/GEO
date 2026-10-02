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
    assert result.answer_shown is None  # always answers, like an LLM platform
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


# ── Task 3: the score stays bit-identical ──────────────────────────────────

def _row(platform, seen, shown=None):
    from app.models.scan_query_result import ScanQueryResult
    return ScanQueryResult(platform=platform, category="recommendation", query_text="q",
                           response_text="" if shown is False else "a", brand_detected=seen,
                           answer_shown=shown, is_control=False)


def _llm_rows():
    return [
        _row("chatgpt", True), _row("chatgpt", False),
        _row("perplexity", True), _row("perplexity", True),
        _row("gemini", False), _row("gemini", False),
        _row("claude", True), _row("claude", False),
    ]


def test_adding_google_surfaces_leaves_ai_citability_and_the_score_unchanged():
    from app.services.scoring_service import (
        compute_ai_citability, compute_geo_score, compute_platform_breakdown,
    )

    client = MagicMock(technical_foundations_verified=True, structured_data_verified=False,
                       brand_authority_score=60, content_quality_score=40)
    llm_only = _llm_rows()
    with_google = llm_only + [
        _row("google_aio", True, True), _row("google_aio", False, False),
        _row("google_ai_mode", True, True), _row("google_ai_mode", True, True),
    ]
    before_bd = compute_platform_breakdown(llm_only)
    after_bd = compute_platform_breakdown(with_google, failed_platforms=[])

    before = compute_ai_citability(llm_only, before_bd)
    after = compute_ai_citability(with_google, after_bd)
    assert after == before == 50.0
    assert compute_geo_score(client, after) == compute_geo_score(client, before)
    # flat-ratio fallback ignores them too
    assert compute_ai_citability(with_google) == compute_ai_citability(llm_only)


def test_breakdown_reports_google_with_its_overview_appearance_rate():
    from app.services.scoring_service import compute_platform_breakdown

    bd = compute_platform_breakdown(_llm_rows() + [
        _row("google_aio", True, True), _row("google_aio", False, False),
        _row("google_aio", False, False), _row("google_ai_mode", False),
    ], failed_platforms=[])

    assert bd["google_aio"] == {"visibility": 33.33, "queries": 3, "detected": 1,
                                "status": "ok", "scored": False, "answers_shown": 1}
    assert bd["google_ai_mode"]["scored"] is False
    assert "answers_shown" not in bd["google_ai_mode"]
    assert bd["chatgpt"]["scored"] is True and "answers_shown" not in bd["chatgpt"]


def test_breakdowns_written_before_the_scored_flag_still_score():
    from app.services.scoring_service import compute_ai_citability

    legacy = {"chatgpt": {"visibility": 40.0, "queries": 5, "detected": 2, "status": "ok"},
              "gemini": {"visibility": 60.0, "queries": 5, "detected": 3, "status": "ok"}}
    assert compute_ai_citability([], legacy) == 50.0


def test_a_client_needs_at_least_one_scored_platform():
    from pydantic import ValidationError

    from app.schemas.client import ClientUpdate

    with pytest.raises(ValidationError, match="at least one of ChatGPT"):
        ClientUpdate(enabled_platforms=["google_aio", "google_ai_mode"])
    ok = ClientUpdate(enabled_platforms=["google_ai_mode", "claude"])
    assert ok.enabled_platforms == ["claude", "google_ai_mode"]


# ── Task 5: headline numbers stay on the scored platforms ──────────────────

def _ns(platform, seen):
    from types import SimpleNamespace
    return SimpleNamespace(platform=platform, brand_detected=seen, competitor_id=None,
                           is_control=False, hallucination_flagged=False)


def test_headline_visibility_helpers_ignore_reported_only_platforms():
    from app.services import alert_service, causality_service, gap_matrix_service, scan_diff_service
    from app.services.scoring_service import scored_results

    llm = [_ns("chatgpt", True), _ns("claude", False)]
    google = [_ns("google_aio", False), _ns("google_aio", False), _ns("google_ai_mode", False)]
    mixed = llm + google

    assert scored_results(mixed) == llm
    assert alert_service._compute_citability(mixed) == alert_service._compute_citability(llm) == 50.0
    assert causality_service._freq(mixed) == causality_service._freq(llm)
    assert gap_matrix_service._visibility(mixed) == gap_matrix_service._visibility(llm)
    assert scan_diff_service._visibility(mixed) == scan_diff_service._visibility(llm)
    # nothing scored at all reads as "no data", not 0%
    assert gap_matrix_service._visibility(google) is None


def test_competitor_page_overall_matches_the_score_but_lists_google_per_platform(db):
    from app.models.scan_query_result import ScanQueryResult
    from app.services.competitor_intelligence_service import compute_competitor_intelligence
    from tests.test_ai_mirror import _client, _competitor, _scan

    client = _client(db)
    rival = _competitor(db, client, "Smile Studio")
    scan = _scan(db, client)
    for platform, seen, comp, shown in [
        ("chatgpt", True, None, None), ("chatgpt", False, None, None),
        ("chatgpt", True, rival, None),
        ("google_aio", False, None, False), ("google_aio", False, None, False),
        ("google_aio", True, rival, True),
    ]:
        db.add(ScanQueryResult(scan_id=scan.id, platform=platform, category="recommendation",
                               query_text="q", response_text="" if shown is False else "a",
                               brand_detected=seen, competitor_id=comp.id if comp else None,
                               answer_shown=shown))
    db.commit()

    intel = compute_competitor_intelligence(client.id, db)
    assert intel.client_ai_citability == 50.0  # chatgpt only
    assert intel.client_platform_visibility == {"chatgpt": 50.0, "google_aio": 0.0}
    [comp] = intel.competitors
    assert comp.ai_citability == 100.0
    assert comp.platform_visibility["google_aio"] == 100.0


# ── Task 7: client-facing surfaces ──────────────────────────────────────────

_BANNED = ("cited", "uncited", "mentioned", "citation rate", "ranking position",
           "visibility gap", "confidence score", "token count", "dataforseo")

_BD = {
    "chatgpt": {"visibility": 50.0, "queries": 4, "detected": 2, "status": "ok", "scored": True},
    "google_aio": {"visibility": 25.0, "queries": 4, "detected": 1, "status": "ok",
                   "scored": False, "answers_shown": 2},
    "google_ai_mode": {"visibility": 100.0, "queries": 4, "detected": 4, "status": "ok",
                       "scored": False},
}


def test_share_view_platforms_mark_google_as_reference_with_overview_rate():
    from app.api.v1.client_view import _view_platforms

    chatgpt, aio, mode = _view_platforms(_BD)
    assert (chatgpt.in_score, chatgpt.ai_overviews_shown, chatgpt.questions_checked) == (True, None, None)
    assert (aio.platform_label, aio.in_score) == ("Google AI Overviews", False)
    assert (aio.ai_overviews_shown, aio.questions_checked) == (2, 4)
    assert (mode.in_score, mode.ai_overviews_shown) == (False, None)
    # breakdowns written before the flag are all scored
    [legacy] = _view_platforms({"gemini": {"visibility": 10.0, "queries": 2, "detected": 1, "status": "ok"}})
    assert legacy.in_score is True


def test_methodology_lists_google_separately_with_a_plain_note():
    from app.services.methodology_service import build_methodology

    m = build_methodology(["chatgpt", "claude", "google_aio", "google_ai_mode"])
    assert m["platforms"] == ["ChatGPT", "Claude"]
    assert m["reported_platforms"] == ["Google AI Overviews", "Google AI Mode"]
    note = m["reported_platforms_note"]
    assert "not yet part of your score" in note
    assert "Not every Google search shows an AI Overview" in note
    assert "Malaysia" in note
    assert not any(term in note.lower() for term in _BANNED)

    plain = build_methodology(["chatgpt"])
    assert plain["reported_platforms"] == [] and plain["reported_platforms_note"] is None


def test_pdf_platform_table_marks_google_as_reference_and_scorecard_leaves_it_out():
    from app.services import report_service as rs
    from tests.test_report_v2 import _minimal_data

    stub = type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})()
    data = _minimal_data(platform_breakdown=_BD)
    html = rs._build_report_html(stub, data)
    section = html[html.index("Platform Breakdown"):].split("<h2>", 1)[0]
    assert "Google AI Overviews" in section and "Google AI Mode" in section
    assert "Google showed an AI Overview for 2 of 4 questions" in section
    assert section.count("not yet part of your score") >= 2
    assert not any(term in section.lower() for term in _BANNED)

    assert "Platform Breakdown" not in rs._build_report_html(stub, _minimal_data())

    scorecard = rs._build_scorecard_html(stub, data, None)
    assert "ChatGPT" in scorecard and "Google AI" not in scorecard
