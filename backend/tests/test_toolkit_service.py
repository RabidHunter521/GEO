from unittest.mock import MagicMock, patch
from app.services.toolkit_service import generate_robots_txt, generate_llms_txt, generate_schema_json


def _fake_client():
    m = MagicMock()
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = "An AI company"
    m.target_audience = "developers"
    m.city = "Kuala Lumpur"
    m.state = "Selangor"
    return m


def test_generate_robots_txt_contains_required_bots():
    client = _fake_client()
    result = generate_robots_txt(client)
    assert "GPTBot" in result
    assert "PerplexityBot" in result
    assert "ClaudeBot" in result
    assert "Google-Extended" in result
    assert "Allow: /" in result


def test_generate_robots_txt_contains_client_domain():
    client = _fake_client()
    result = generate_robots_txt(client)
    assert "acme.com" in result


def test_generate_llms_txt_calls_claude_and_returns_content():
    client = _fake_client()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Acme Corp\n> tagline")]

    with patch("app.services.toolkit_service._anthropic_client") as mock_client_fn:
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_anthropic
        result = generate_llms_txt(client)

    assert result == "# Acme Corp\n> tagline"
    mock_anthropic.messages.create.assert_called_once()


def test_generate_schema_json_calls_claude_and_returns_content():
    client = _fake_client()
    schema = '{"@context": "https://schema.org", "@graph": []}'
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=schema)]

    with patch("app.services.toolkit_service._anthropic_client") as mock_client_fn:
        mock_anthropic = MagicMock()
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_anthropic
        result = generate_schema_json(client)

    assert result == schema
    mock_anthropic.messages.create.assert_called_once()
