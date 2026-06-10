from unittest.mock import MagicMock, patch

from app.services import position_extraction as pe


def _reply(text):
    resp = MagicMock()
    block = MagicMock()
    block.text = text
    resp.content = [block]
    return resp


def _patch_client(reply_text):
    client = MagicMock()
    client.messages.create.return_value = _reply(reply_text)
    return patch.object(pe, "anthropic_client", return_value=client)


def test_returns_position_number():
    with _patch_client("2"):
        assert pe.extract_position("1. A\n2. ACME\n3. B", "ACME") == 2


def test_returns_none_for_none_reply():
    with _patch_client("none"):
        assert pe.extract_position("ACME is a fine company.", "ACME") is None


def test_strips_extra_text_around_number():
    with _patch_client("#3") as _:
        assert pe.extract_position("some list", "ACME") == 3


def test_empty_response_short_circuits_without_api_call():
    client = MagicMock()
    with patch.object(pe, "anthropic_client", return_value=client):
        assert pe.extract_position("", "ACME") is None
    client.messages.create.assert_not_called()


def test_zero_position_treated_as_none():
    with _patch_client("0"):
        assert pe.extract_position("list", "ACME") is None
