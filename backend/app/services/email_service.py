import resend
from app.core.config import settings


def send_email(to: str, subject: str, html_body: str) -> None:
    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": "contact@seenby.my",
        "to": [to],
        "subject": subject,
        "html": html_body,
    })
