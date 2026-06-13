import uuid
from unittest.mock import MagicMock, patch


# ── send_telegram ─────────────────────────────────────────────────────────────

def test_send_telegram_noop_when_unconfigured():
    from app.services import telegram_service
    with patch.object(telegram_service.settings, "TELEGRAM_BOT_TOKEN", ""), \
         patch.object(telegram_service.settings, "TELEGRAM_CHAT_ID", ""), \
         patch("app.services.telegram_service.httpx.post") as mock_post:
        telegram_service.send_telegram("hello")
    mock_post.assert_not_called()


def test_send_telegram_noop_when_chat_id_missing():
    from app.services import telegram_service
    with patch.object(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "tok"), \
         patch.object(telegram_service.settings, "TELEGRAM_CHAT_ID", ""), \
         patch("app.services.telegram_service.httpx.post") as mock_post:
        telegram_service.send_telegram("hello")
    mock_post.assert_not_called()


def test_send_telegram_posts_when_configured():
    from app.services import telegram_service
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch.object(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "tok123"), \
         patch.object(telegram_service.settings, "TELEGRAM_CHAT_ID", "456"), \
         patch("app.services.telegram_service.httpx.post", return_value=mock_resp) as mock_post:
        telegram_service.send_telegram("<b>hi</b>")
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "bottok123/sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "456"
    assert kwargs["json"]["text"] == "<b>hi</b>"
    assert kwargs["json"]["parse_mode"] == "HTML"


def test_send_telegram_swallows_exceptions():
    from app.services import telegram_service
    with patch.object(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "tok"), \
         patch.object(telegram_service.settings, "TELEGRAM_CHAT_ID", "456"), \
         patch("app.services.telegram_service.httpx.post", side_effect=RuntimeError("network down")):
        # Must not raise
        telegram_service.send_telegram("hi")


# ── _dispatch_admin_alert fan-out ────────────────────────────────────────────

def test_dispatch_sends_email_and_telegram():
    from app.services.alert_service import _dispatch_admin_alert
    with patch("app.services.alert_service.send_email") as mock_email, \
         patch("app.services.alert_service.send_telegram") as mock_tg:
        _dispatch_admin_alert("subj", "<p>body</p>", "tg text")
    mock_email.assert_called_once_with(to="contact@seenby.my", subject="subj", html_body="<p>body</p>")
    mock_tg.assert_called_once_with("tg text")


def test_score_drop_alert_also_pushes_telegram():
    from app.services.alert_service import check_score_drop_alert
    from app.models.client import Client

    client = MagicMock(spec=Client)
    client.id = uuid.uuid4()
    client.name = "Test Brand"
    client.score_drop_threshold = 35

    current = MagicMock(); current.overall_score = 30.0
    prev = MagicMock(); prev.overall_score = 40.0

    db = MagicMock()
    with patch("app.services.alert_service.send_email"), \
         patch("app.services.alert_service.send_telegram") as mock_tg:
        check_score_drop_alert(client, current, prev, db)
    mock_tg.assert_called_once()
    text = mock_tg.call_args[0][0]
    assert "Test Brand" in text
    assert "40→30" in text


def test_telegram_transport_failure_does_not_break_alert():
    """End-to-end contract: a Telegram network failure (httpx raising) is
    swallowed by send_telegram, so the alert still emails and commits."""
    from app.services.alert_service import check_score_drop_alert
    from app.services import telegram_service
    from app.models.client import Client

    client = MagicMock(spec=Client)
    client.id = uuid.uuid4()
    client.name = "Test Brand"
    client.score_drop_threshold = 35
    current = MagicMock(); current.overall_score = 30.0
    prev = MagicMock(); prev.overall_score = 40.0

    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_email, \
         patch.object(telegram_service.settings, "TELEGRAM_BOT_TOKEN", "tok"), \
         patch.object(telegram_service.settings, "TELEGRAM_CHAT_ID", "456"), \
         patch("app.services.telegram_service.httpx.post", side_effect=RuntimeError("network down")):
        check_score_drop_alert(client, current, prev, db)

    mock_email.assert_called_once()
    db.commit.assert_called_once()
