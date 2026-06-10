from unittest.mock import MagicMock, patch
from app.services.verification_crawler import (
    verify_llms_txt,
    verify_schema_json,
    verify_robots_txt,
    _domain_base,
)


def test_domain_base_strips_path():
    assert _domain_base("https://acme.com/about") == "https://acme.com"


def test_domain_base_keeps_subdomain():
    assert _domain_base("https://www.acme.com") == "https://www.acme.com"


def test_domain_base_adds_https_when_no_scheme():
    assert _domain_base("acme.com") == "https://acme.com"


def test_verify_llms_txt_returns_true_on_200_with_content():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "# Acme Corp\n> tagline"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_llms_txt("https://acme.com") is True


def test_verify_llms_txt_returns_false_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = ""

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_llms_txt("https://acme.com") is False


def test_verify_llms_txt_returns_false_on_exception():
    with patch("app.services.verification_crawler.httpx.get", side_effect=Exception("timeout")):
        assert verify_llms_txt("https://acme.com") is False


def test_verify_schema_json_returns_true_on_valid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"@context": "https://schema.org"}

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is True


def test_verify_schema_json_returns_false_on_invalid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("not json")

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is False


def test_verify_schema_json_returns_false_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_schema_json("https://acme.com") is False


def test_verify_robots_txt_returns_true_when_gptbot_present():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "User-agent: *\nDisallow: /private\n\nUser-agent: GPTBot\nAllow: /"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_robots_txt("https://acme.com") is True


def test_verify_robots_txt_returns_false_when_gptbot_absent():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "User-agent: *\nDisallow:"

    with patch("app.services.verification_crawler.httpx.get", return_value=mock_resp):
        assert verify_robots_txt("https://acme.com") is False


def test_verify_robots_txt_returns_false_on_exception():
    with patch("app.services.verification_crawler.httpx.get", side_effect=Exception("refused")):
        assert verify_robots_txt("https://acme.com") is False
