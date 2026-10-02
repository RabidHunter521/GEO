"""Lead-source attribution: classification, click recording, answers."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.attribution_signal import AttributionSignal
from app.models.client import Client
from app.models.conversion_event import ConversionEvent
from app.services import attribution_service as svc

BROWSER_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1"


@pytest.fixture
def account(db):
    client = Client(
        name="Klinik Sihat",
        website="https://kliniksihat.example.com",
        industry="Clinic",
        contact_email="hello@example.com",
    )
    db.add(client)
    db.commit()
    return client


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("ChatGPT", "ChatGPT"),
        ("I asked chat gpt for a clinic", "ChatGPT"),
        ("Google AI Overview", "Google AI Overviews"),
        ("meta ai on whatsapp", "Meta AI"),
        ("Perplexity", "Perplexity"),
        ("AI", "AI assistant"),
        ("Google", None),
        ("google search", None),
        ("Kawan recommend", None),
        ("Facebook", None),
        ("email", None),  # "ai" inside a word never matches
        ("Mailchimp newsletter", None),
    ],
)
def test_classify_answer(answer, expected):
    assert svc.classify_answer(answer) == expected


def test_classify_visit_prefers_landing_referrer_then_utm():
    assert svc.classify_visit(
        landing_referrer="chatgpt.com", landing_utm=None, click_referrer=None
    ) == ("ChatGPT", "referrer")
    assert svc.classify_visit(
        landing_referrer="www.google.com", landing_utm="chatgpt.com", click_referrer=None
    ) == ("ChatGPT", "utm")
    assert svc.classify_visit(
        landing_referrer="", landing_utm="perplexity", click_referrer=None
    ) == ("Perplexity", "utm")
    # "ai" alone is too loose to trust in a utm tag.
    assert svc.classify_visit(landing_referrer="", landing_utm="ai", click_referrer=None) == (None, None)
    assert svc.classify_visit(
        landing_referrer="https://www.perplexity.ai/search?q=x", landing_utm=None, click_referrer=None
    ) == ("Perplexity", "referrer")
    assert svc.classify_visit(
        landing_referrer="www.google.com", landing_utm="", click_referrer="https://kliniksihat.example.com/"
    ) == (None, None)


def test_normalize_whatsapp_number():
    assert svc.normalize_whatsapp_number("+60 12-345 6789") == "60123456789"
    assert svc.normalize_whatsapp_number("") is None
    with pytest.raises(svc.AttributionValidationError):
        svc.normalize_whatsapp_number("012-345 6789")
    with pytest.raises(svc.AttributionValidationError):
        svc.normalize_whatsapp_number("call me")


def test_ai_click_writes_attributed_conversion(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    url = svc.record_whatsapp_click(
        setting.click_token,
        db,
        fallback_url="https://wa.me/60111111111?text=Hi",
        landing_referrer="chatgpt.com",
        visitor_ip="203.0.113.5",
        user_agent=BROWSER_UA,
    )
    assert url == "https://wa.me/60111111111?text=Hi"

    signal = db.query(AttributionSignal).one()
    assert signal.ai_platform == "ChatGPT"
    assert signal.match_reason == "referrer"
    event = db.get(ConversionEvent, signal.conversion_event_id)
    assert event.evidence_level == "attributed"
    assert event.event_type == "whatsapp_click"
    assert event.source == "whatsapp_link"
    assert event.value_minor == 0


def test_non_ai_click_is_counted_but_not_in_ledger(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    svc.record_whatsapp_click(
        setting.click_token,
        db,
        fallback_url="https://wa.me/60111111111",
        landing_referrer="www.google.com",
        visitor_ip="203.0.113.5",
        user_agent=BROWSER_UA,
    )
    signal = db.query(AttributionSignal).one()
    assert signal.ai_platform is None
    assert signal.conversion_event_id is None
    assert db.query(ConversionEvent).count() == 0


def test_repeat_click_from_same_visitor_counts_once(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    for _ in range(3):
        svc.record_whatsapp_click(
            setting.click_token,
            db,
            fallback_url="https://wa.me/60111111111",
            landing_referrer="chatgpt.com",
            visitor_ip="203.0.113.5",
            user_agent=BROWSER_UA,
        )
    assert db.query(AttributionSignal).count() == 1
    assert db.query(ConversionEvent).count() == 1
    # A different visitor is a separate enquiry.
    svc.record_whatsapp_click(
        setting.click_token,
        db,
        fallback_url="https://wa.me/60111111111",
        visitor_ip="198.51.100.7",
        user_agent=BROWSER_UA,
    )
    assert db.query(AttributionSignal).count() == 2


def test_bots_and_disabled_tracking_redirect_without_recording(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    url = svc.record_whatsapp_click(
        setting.click_token,
        db,
        fallback_url="https://wa.me/60111111111",
        landing_referrer="chatgpt.com",
        visitor_ip="203.0.113.5",
        user_agent="WhatsApp/2.23.20.0 A",
    )
    assert url == "https://wa.me/60111111111"
    setting.tracking_enabled = False
    db.commit()
    url = svc.record_whatsapp_click(
        setting.click_token,
        db,
        fallback_url="https://wa.me/60111111111",
        visitor_ip="203.0.113.5",
        user_agent=BROWSER_UA,
    )
    assert url == "https://wa.me/60111111111"
    assert db.query(AttributionSignal).count() == 0


def test_redirect_never_leaves_whatsapp(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    for evil in (
        "https://evil.example.com/phish",
        "http://wa.me/60111111111",
        "https://wa.me.evil.com/x",
        "javascript:alert(1)",
        "https://user@wa.me/601",
    ):
        assert svc.record_whatsapp_click(setting.click_token, db, fallback_url=evil) is None
    # No fallback and no configured number -> nowhere safe to go.
    assert svc.record_whatsapp_click(setting.click_token, db) is None
    svc.update_setting(
        account.id, db, whatsapp_number="+60 12 345 6789", whatsapp_message="Hi, saya nak tanya",
        tracking_enabled=True,
    )
    assert (
        svc.record_whatsapp_click(setting.click_token, db, fallback_url="https://evil.example.com")
        == "https://wa.me/60123456789?text=Hi%2C%20saya%20nak%20tanya"
    )
    assert svc.record_whatsapp_click("not-a-token", db) is None


def test_answer_is_idempotent_and_attributed(db, account):
    when = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    signal, created = svc.record_answer(
        account.id, db, answer="ChatGPT", submission_id="form-1", source="webhook",
        occurred_at=when, event_type="booking", value_minor=15000,
    )
    assert created
    again, created_again = svc.record_answer(
        account.id, db, answer="Changed my mind: Google", submission_id="form-1", source="webhook",
    )
    assert not created_again
    assert again.id == signal.id
    assert db.query(ConversionEvent).count() == 1
    event = db.query(ConversionEvent).one()
    assert event.evidence_level == "attributed"
    assert event.source == "lead_form"
    assert event.event_type == "booking"
    assert event.value_minor == 15000
    assert event.occurred_at == datetime(2026, 9, 1, 10, 0)


def test_non_ai_answer_and_future_timestamp(db, account):
    future = datetime.now(timezone.utc) + timedelta(days=10)
    signal, _ = svc.record_answer(
        account.id, db, answer="Facebook ad", submission_id=None, source="manual", occurred_at=future,
    )
    assert signal.ai_platform is None
    assert signal.occurred_at <= datetime.now(timezone.utc).replace(tzinfo=None)
    assert db.query(ConversionEvent).count() == 0


def test_summary_counts_share_by_channel(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    svc.record_whatsapp_click(setting.click_token, db, fallback_url="https://wa.me/601",
                              landing_referrer="chatgpt.com", visitor_ip="1.1.1.1", user_agent=BROWSER_UA)
    svc.record_whatsapp_click(setting.click_token, db, fallback_url="https://wa.me/601",
                              visitor_ip="2.2.2.2", user_agent=BROWSER_UA)
    svc.record_answer(account.id, db, answer="Gemini", submission_id="a", source="webhook")
    summary = svc.summarize(account.id, db)
    assert summary["channels"]["whatsapp_click"] == {
        "total": 2, "ai_attributed": 1, "by_platform": {"ChatGPT": 1}
    }
    assert summary["channels"]["heard_about_us"]["by_platform"] == {"Gemini": 1}
    assert len(summary["recent"]) == 3


def test_webhook_secret_lookup(db, account):
    secret, _ = svc.rotate_webhook_secret(account.id, db)
    assert svc.find_setting_by_secret(secret, db).client_id == account.id
    assert svc.find_setting_by_secret("sbwh_wrong", db) is None
    new_secret, _ = svc.rotate_webhook_secret(account.id, db)
    assert svc.find_setting_by_secret(secret, db) is None
    assert svc.find_setting_by_secret(new_secret, db) is not None


def test_snippet_points_at_tracked_link(db, account):
    setting = svc.get_or_create_setting(account.id, db)
    snippet = svc.build_website_snippet(setting)
    assert f"/wa/{setting.click_token}" in snippet
    assert snippet.startswith("<script>") and snippet.endswith("</script>")
