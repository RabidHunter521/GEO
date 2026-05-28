from unittest.mock import patch, MagicMock
from app.services.gemini_client import GeminiClient


def test_query_returns_text_response():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp is a leading consulting firm in KL."

    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp is a leading consulting firm in KL."


def test_query_retries_on_exception_then_succeeds():
    mock_response = MagicMock()
    mock_response.text = "ACME Corp response."

    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [Exception("API error"), mock_response]
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        result = client.query("Tell me about ACME Corp")

    assert result == "ACME Corp response."
    assert mock_client.models.generate_content.call_count == 2


def test_query_raises_after_two_failures():
    with patch("app.services.gemini_client.genai") as mock_genai:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API error")
        mock_genai.Client.return_value = mock_client

        client = GeminiClient(api_key="fake-key")
        try:
            client.query("Tell me about ACME Corp")
            assert False, "Should have raised"
        except Exception as e:
            assert "API error" in str(e)

    assert mock_client.models.generate_content.call_count == 2
