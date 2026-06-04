from unittest.mock import patch, MagicMock


def _make_client(name="Test Brand", industry="Technology"):
    c = MagicMock()
    c.name = name
    c.industry = industry
    return c


def test_returns_static_tip_when_score_change_below_threshold():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    result = get_digest_action(
        client=client,
        current_ai_citability=62.0,
        prev_ai_citability=60.0,  # change = 2pts, below 5pt threshold
    )
    assert result == DIGEST_STATIC_TIPS["fair"]


def test_returns_static_tip_when_no_previous_score():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    result = get_digest_action(
        client=client,
        current_ai_citability=30.0,
        prev_ai_citability=None,
    )
    assert result == DIGEST_STATIC_TIPS["low"]


def test_calls_claude_when_score_increases_by_5_or_more():
    from app.services.claude_action import get_digest_action
    mock_content = MagicMock()
    mock_content.text = "Publish a blog post featuring your brand name."
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = get_digest_action(
            client=client,
            current_ai_citability=75.0,
            prev_ai_citability=60.0,  # change = 15pts, above threshold
        )
    assert result == "Publish a blog post featuring your brand name."
    mock_cls.return_value.messages.create.assert_called_once()


def test_calls_claude_when_score_drops_by_5_or_more():
    from app.services.claude_action import get_digest_action
    mock_content = MagicMock()
    mock_content.text = "Add your brand to three new business directories this week."
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = get_digest_action(
            client=client,
            current_ai_citability=55.0,
            prev_ai_citability=70.0,  # drop = 15pts, above threshold
        )
    assert result == "Add your brand to three new business directories this week."


def test_falls_back_to_static_tip_when_claude_raises():
    from app.services.claude_action import get_digest_action
    from app.core.constants import DIGEST_STATIC_TIPS
    client = _make_client()
    with patch("app.services.claude_action.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = Exception("API error")
        result = get_digest_action(
            client=client,
            current_ai_citability=75.0,
            prev_ai_citability=60.0,  # 15pt change triggers Claude, but it raises
        )
    # 75 is in "good" band (65-79)
    assert result == DIGEST_STATIC_TIPS["good"]
