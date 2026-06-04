from unittest.mock import patch, MagicMock
from app.services import email_service


def test_send_email_calls_resend_with_correct_params():
    mock_emails = MagicMock()
    with patch("app.services.email_service.resend") as mock_resend:
        mock_resend.Emails = mock_emails
        email_service.send_email(
            to="client@example.com",
            subject="Your update",
            html_body="<p>Hello</p>",
        )
    mock_emails.send.assert_called_once_with({
        "from": "contact@seenby.my",
        "to": ["client@example.com"],
        "subject": "Your update",
        "html": "<p>Hello</p>",
    })
