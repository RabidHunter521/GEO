"""Client-facing notification channels (used by win_notification_service).

A channel turns one ClientMessage into a delivery. Email is the only live
channel today. WhatsApp sits behind the same interface so it can be switched
on without touching win detection: implement `WhatsAppChannel.send` against a
provider and make `is_available` true once the client has a number on file.

Admin alerts are NOT sent through here — they go to ALERTS_EMAIL / Telegram via
alert_service. These channels only ever reach a client.
"""
from dataclasses import dataclass
from typing import Protocol

from app.models.client import Client
from app.services.email_service import send_email


@dataclass(frozen=True)
class ClientMessage:
    subject: str
    html_body: str
    # Plain-text rendering for channels without HTML (WhatsApp, SMS).
    text_body: str


class NotificationChannel(Protocol):
    name: str

    def is_available(self, client: Client) -> bool:
        """True when this channel can reach this client right now."""
        ...

    def send(self, client: Client, message: ClientMessage) -> None:
        """Deliver, or raise. Callers isolate each channel's failure."""
        ...


class EmailChannel:
    name = "email"

    def is_available(self, client: Client) -> bool:
        return bool(client.contact_email)

    def send(self, client: Client, message: ClientMessage) -> None:
        send_email(to=client.contact_email, subject=message.subject, html_body=message.html_body)


class WhatsAppChannel:
    """Placeholder adapter: SeenBy has no WhatsApp integration yet.

    To switch it on: pick a provider (Meta WhatsApp Cloud API or Twilio), get a
    message template approved (business-initiated WhatsApp messages must use
    one), store the client's opted-in WhatsApp number per client (encrypted,
    never shown on a client-facing view), then implement `send` with
    `message.text_body` and return True from `is_available` when that number
    exists. Until then it is never available, so nothing is sent.
    """

    name = "whatsapp"

    def is_available(self, client: Client) -> bool:
        return False

    def send(self, client: Client, message: ClientMessage) -> None:
        raise NotImplementedError("WhatsApp delivery is not integrated yet.")


CLIENT_CHANNELS: tuple[NotificationChannel, ...] = (EmailChannel(), WhatsAppChannel())
