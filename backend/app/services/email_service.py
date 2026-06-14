import resend

from app.core.config import settings

# Configure the key and a bounded HTTP timeout once at import — not on every
# send. The default client allows 30s; 10s is plenty for a transactional send
# and keeps a slow Resend call from hanging a request/worker.
resend.api_key = settings.RESEND_API_KEY
resend.default_http_client = resend.RequestsClient(timeout=10)


def send_email(to: str, subject: str, html_body: str) -> None:
    resend.Emails.send({
        "from": "contact@seenby.my",
        "to": [to],
        "subject": subject,
        "html": html_body,
    })
