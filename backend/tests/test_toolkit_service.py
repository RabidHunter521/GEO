import json
import pytest
from unittest.mock import MagicMock, patch
from app.services.toolkit_service import (
    _strip_code_fences,
    generate_robots_txt,
    generate_llms_txt,
    generate_schema_json,
    generate_toolkit_files,
)

_VALID_SCHEMA = '{"@context": "https://schema.org", "@graph": []}'


def _fake_client():
    m = MagicMock()
    m.id = "test-client-id"
    m.name = "Acme Corp"
    m.website = "https://acme.com"
    m.industry = "Technology"
    m.description = "An AI company"
    m.target_audience = "developers"
    m.city = "Kuala Lumpur"
    m.state = "Selangor"
    return m


def _mock_ac(text: str):
    """Return a mock Anthropic client whose messages.create always returns text."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_ac = MagicMock()
    mock_ac.messages.create.return_value = mock_response
    return mock_ac


# ── _strip_code_fences ────────────────────────────────────────────────────────

def test_strip_code_fences_removes_json_fence():
    raw = '```json\n{"@context": "https://schema.org"}\n```'
    assert _strip_code_fences(raw) == '{"@context": "https://schema.org"}'


def test_strip_code_fences_removes_plain_fence():
    raw = '```\n{"key": "val"}\n```'
    assert _strip_code_fences(raw) == '{"key": "val"}'


def test_strip_code_fences_is_noop_on_clean_json():
    raw = '{"@context": "https://schema.org"}'
    assert _strip_code_fences(raw) == raw


def test_strip_code_fences_trims_surrounding_whitespace():
    raw = '  \n```json\n{"k": 1}\n```  \n'
    assert _strip_code_fences(raw) == '{"k": 1}'


# ── generate_robots_txt ───────────────────────────────────────────────────────

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


# ── generate_llms_txt ─────────────────────────────────────────────────────────

def test_generate_llms_txt_calls_claude_and_returns_content():
    client = _fake_client()

    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_ac("# Acme Corp\n> tagline")):
        result = generate_llms_txt(client)

    assert result == "# Acme Corp\n> tagline"


# ── generate_schema_json ──────────────────────────────────────────────────────

def test_generate_schema_json_returns_valid_json():
    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_ac(_VALID_SCHEMA)):
        result = generate_schema_json(_fake_client())

    assert result == _VALID_SCHEMA
    json.loads(result)  # must be parseable


def test_generate_schema_json_strips_code_fences_before_storing():
    fenced = f"```json\n{_VALID_SCHEMA}\n```"

    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_ac(fenced)):
        result = generate_schema_json(_fake_client())

    parsed = json.loads(result)
    assert parsed["@context"] == "https://schema.org"


def test_generate_schema_json_retries_on_invalid_json_then_succeeds():
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        msg.content = [MagicMock(text="not json" if call_count == 1 else _VALID_SCHEMA)]
        return msg

    mock_ac = MagicMock()
    mock_ac.messages.create.side_effect = side_effect

    with patch("app.services.toolkit_service._anthropic_client", return_value=mock_ac):
        result = generate_schema_json(_fake_client())

    assert call_count == 2
    assert json.loads(result)["@context"] == "https://schema.org"


def test_generate_schema_json_raises_after_two_invalid_attempts():
    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_ac("not json at all")):
        with pytest.raises(ValueError, match="invalid JSON"):
            generate_schema_json(_fake_client())


# ── generate_toolkit_files ────────────────────────────────────────────────────

def test_generate_toolkit_files_returns_all_three_keys():
    client = _fake_client()

    # llms_txt gets plain text; schema_json must be valid JSON
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        # Both calls return something valid for their type —
        # first call is llms (plain text fine), second is schema (needs JSON)
        msg.content = [MagicMock(text=_VALID_SCHEMA)]
        return msg

    mock_ac = MagicMock()
    mock_ac.messages.create.side_effect = side_effect

    with patch("app.services.toolkit_service._anthropic_client", return_value=mock_ac):
        result = generate_toolkit_files(client)

    assert set(result.keys()) == {"llms_txt", "schema_json", "robots_txt"}
    assert "GPTBot" in result["robots_txt"]


def test_generate_toolkit_files_propagates_schema_error():
    with patch("app.services.toolkit_service._anthropic_client", return_value=_mock_ac("bad json")):
        with pytest.raises(ValueError, match="invalid JSON"):
            generate_toolkit_files(_fake_client())
