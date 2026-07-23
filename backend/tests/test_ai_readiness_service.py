import uuid
from unittest.mock import MagicMock, patch

from app.services.ai_readiness_service import (
    check_robots_ai_bot_access,
    check_homepage_schema,
    check_site_ai_readiness,
    compute_competitor_ai_readiness,
)
from app.core.constants import AI_CRAWLER_BOTS


def _resp(status_code, text=""):
    m = MagicMock()
    m.status_code = status_code
    m.text = text
    return m


# ── robots.txt AI-bot blocking ──────────────────────────────────────────


def test_robots_detects_bot_specific_disallow():
    robots = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /"
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, robots)):
        assert check_robots_ai_bot_access("https://rival.com") == ["GPTBot"]


def test_robots_wildcard_disallow_blocks_all_bots():
    robots = "User-agent: *\nDisallow: /"
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, robots)):
        blocked = check_robots_ai_bot_access("https://rival.com")
    assert set(blocked) == set(AI_CRAWLER_BOTS)


def test_robots_returns_empty_when_all_allowed():
    robots = "User-agent: *\nAllow: /\nDisallow: /wp-admin/"
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, robots)):
        assert check_robots_ai_bot_access("https://rival.com") == []


def test_robots_returns_empty_on_404():
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(404)):
        assert check_robots_ai_bot_access("https://rival.com") == []


def test_robots_returns_empty_on_exception():
    with patch("app.services.ai_readiness_service.safe_get", side_effect=Exception("timeout")):
        assert check_robots_ai_bot_access("https://rival.com") == []


# ── homepage schema.org detection ───────────────────────────────────────


def test_homepage_schema_extracts_type_from_ld_json():
    html = '<script type="application/ld+json">{"@type": "MedicalClinic"}</script>'
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, html)):
        assert check_homepage_schema("https://rival.com") == ["MedicalClinic"]


def test_homepage_schema_handles_graph_array():
    html = (
        '<script type="application/ld+json">'
        '{"@graph": [{"@type": "Organization"}, {"@type": "WebSite"}]}'
        "</script>"
    )
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, html)):
        assert check_homepage_schema("https://rival.com") == ["Organization", "WebSite"]


def test_homepage_schema_returns_empty_when_absent():
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, "<html></html>")):
        assert check_homepage_schema("https://rival.com") == []


def test_homepage_schema_returns_empty_on_malformed_json():
    html = '<script type="application/ld+json">{not valid json</script>'
    with patch("app.services.ai_readiness_service.safe_get", return_value=_resp(200, html)):
        assert check_homepage_schema("https://rival.com") == []


def test_homepage_schema_returns_empty_on_exception():
    with patch("app.services.ai_readiness_service.safe_get", side_effect=Exception("boom")):
        assert check_homepage_schema("https://rival.com") == []


# ── per-site orchestration ───────────────────────────────────────────────


def test_check_site_ai_readiness_no_website_marks_unchecked():
    result = check_site_ai_readiness("Rival Co", None)
    assert result.checked is False
    assert result.name == "Rival Co"
    assert result.blocked_ai_bots == []
    assert result.has_llms_txt is False
    assert result.schema_types == []


def test_check_site_ai_readiness_combines_all_checks():
    with (
        patch(
            "app.services.ai_readiness_service.check_robots_ai_bot_access",
            return_value=["GPTBot"],
        ),
        patch("app.services.ai_readiness_service.verify_llms_txt", return_value=True),
        patch(
            "app.services.ai_readiness_service.check_homepage_schema",
            return_value=["Organization"],
        ),
    ):
        result = check_site_ai_readiness("Rival Co", "https://rival.com")
    assert result.checked is True
    assert result.blocked_ai_bots == ["GPTBot"]
    assert result.has_llms_txt is True
    assert result.schema_types == ["Organization"]


# ── batch orchestration isolates per-site failures ───────────────────────


def test_compute_competitor_ai_readiness_isolates_per_site_failures():
    client_id = uuid.uuid4()
    fake_client = MagicMock()
    fake_client.name = "Medilink"
    fake_client.website = "https://medilinkhealthcare.my"

    ok_competitor = MagicMock()
    ok_competitor.id = uuid.uuid4()
    ok_competitor.name = "Care Clinics"
    ok_competitor.website = "https://careclinics.com.my"

    broken_competitor = MagicMock()
    broken_competitor.id = uuid.uuid4()
    broken_competitor.name = "Down Site"
    broken_competitor.website = "https://down-site.example"

    mock_db = MagicMock()
    mock_db.get.return_value = fake_client
    mock_db.query.return_value.filter.return_value.all.return_value = [
        ok_competitor,
        broken_competitor,
    ]

    def fake_check(name, website, competitor_id=None):
        if name == "Down Site":
            raise RuntimeError("network exploded")
        from app.schemas.ai_readiness import SiteAIReadiness

        return SiteAIReadiness(
            name=name,
            website=website,
            checked=True,
            has_llms_txt=False,
            blocked_ai_bots=[],
            schema_types=[],
            competitor_id=competitor_id,
        )

    with patch(
        "app.services.ai_readiness_service.check_site_ai_readiness",
        side_effect=fake_check,
    ):
        result = compute_competitor_ai_readiness(client_id, mock_db)

    assert result.client.name == "Medilink"
    assert len(result.competitors) == 2
    ok_result = next(c for c in result.competitors if c.name == "Care Clinics")
    broken_result = next(c for c in result.competitors if c.name == "Down Site")
    assert ok_result.checked is True
    assert broken_result.checked is False


# ── JSON-LD parsing helpers ──────────────────────────────────────────────────


def test_parse_jsonld_scripts_flattens_graph():
    from app.services.ai_readiness_service import parse_jsonld_scripts
    html = ('<html><head><script type="application/ld+json">'
            '{"@context": "https://schema.org", "@graph": ['
            '{"@type": "Organization", "name": "Acme"},'
            '{"@type": "FAQPage"}]}</script></head></html>')
    items = parse_jsonld_scripts(html)
    assert len(items) == 2
    assert items[0]["@type"] == "Organization"


def test_parse_jsonld_scripts_skips_malformed_json():
    from app.services.ai_readiness_service import parse_jsonld_scripts
    html = ('<script type="application/ld+json">{not json}</script>'
            '<script type="application/ld+json">{"@type": "WebSite"}</script>')
    items = parse_jsonld_scripts(html)
    assert len(items) == 1


def test_jsonld_types_from_handles_type_lists():
    from app.services.ai_readiness_service import jsonld_types_from
    types = jsonld_types_from([{"@type": ["Dentist", "LocalBusiness"]}, {"@type": "WebSite"}, {}])
    assert types == ["Dentist", "LocalBusiness", "WebSite"]
