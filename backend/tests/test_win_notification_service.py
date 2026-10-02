"""Client win notifications: detection rules, dedupe, and delivery.

No real message is ever sent: every test injects fake channels or patches
send_email.
"""
import re
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from app.core.constants import SCORE_VERSION
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.client_win import ClientWin
from app.models.geo_score import GeoScore
from app.models.scan import Scan
from app.models.scan_query_result import ScanQueryResult
from app.services.notification_channels import EmailChannel, WhatsAppChannel
from app.services.win_notification_service import detect_wins, process_client_wins

Q = "best dental clinic in Kuala Lumpur"
T0 = datetime(2026, 9, 1, 9, 0)


class FakeChannel:
    def __init__(self, name="fake", available=True, fail=False):
        self.name = name
        self.available = available
        self.fail = fail
        self.sent = []

    def is_available(self, client):
        return self.available

    def send(self, client, message):
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append(message)


def _client(db, enabled=True, **kw):
    c = Client(
        name="Klinik Acme", website="https://acme.my", industry="Dental",
        contact_email="owner@acme.example", win_notifications_enabled=enabled, **kw,
    )
    db.add(c)
    db.commit()
    return c


def _scan(db, client, days, rows, version=SCORE_VERSION):
    """rows: list of (platform, category, query, seen, position[, response])."""
    s = Scan(client_id=client.id, status="completed", completed_at=T0 + timedelta(days=days))
    db.add(s)
    db.flush()
    db.add(GeoScore(client_id=client.id, scan_id=s.id, score_version=version))
    for row in rows:
        platform, category, query, seen, position = row[:5]
        response = row[5] if len(row) > 5 else "an answer"
        db.add(ScanQueryResult(
            scan_id=s.id, platform=platform, category=category, query_text=query,
            response_text=response, brand_detected=seen, recommendation_position=position,
        ))
    db.commit()
    return s


def _history(db, client, states, platform="chatgpt", category="recommendation", query=Q):
    """states oldest-first: each is (seen, position)."""
    scans = []
    for i, (seen, pos) in enumerate(states):
        scans.append(_scan(db, client, i * 7, [(platform, category, query, seen, pos)]))
    return scans


def test_recommended_win_fires_after_two_confirming_scans(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 3), (True, 2)])
    ch = FakeChannel()

    rows = process_client_wins(client.id, scans[-1].id, db, channels=(ch,))

    assert [(r.kind, r.recommendation_position, r.status) for r in rows] == [("recommended", 2, "sent")]
    assert len(ch.sent) == 1
    msg = ch.sent[0]
    assert msg.subject == f'Good news: ChatGPT now recommends Klinik Acme for "{Q}"'
    assert "AI Search Ranking #2" in msg.html_body
    assert "08 Sep 2026 and 15 Sep 2026" in msg.text_body
    events = {a.event_type for a in db.query(ActivityLog).all()}
    assert {"client_win_detected", "win_notification_sent"} <= events


def test_single_new_observation_is_not_a_win(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (False, None), (True, 1)])
    assert process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),)) == []


def test_needs_a_baseline_scan(db):
    client = _client(db)
    scans = _history(db, client, [(True, 1), (True, 1)])
    assert process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),)) == []


def test_already_recommended_before_is_not_a_win(db):
    client = _client(db)
    scans = _history(db, client, [(True, 1), (True, 1), (True, 1)])
    assert process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),)) == []


def test_seen_win_and_upgrade_to_recommended(db):
    client = _client(db)
    # Not seen -> seen (unranked) twice: a "seen" win.
    _scan(db, client, 0, [("gemini", "local", Q, False, None), ("claude", "local", Q, True, None)])
    _scan(db, client, 7, [("gemini", "local", Q, True, None), ("claude", "local", Q, True, 4)])
    s3 = _scan(db, client, 14, [("gemini", "local", Q, True, None), ("claude", "local", Q, True, 2)])
    ch = FakeChannel()

    rows = process_client_wins(client.id, s3.id, db, channels=(ch,))

    kinds = {(r.platform, r.kind) for r in rows}
    # Claude was already seen but newly placed in the list: a recommended win.
    assert kinds == {("gemini", "seen"), ("claude", "recommended")}
    assert ch.sent[0].subject == "Good news: Klinik Acme has 2 new wins in AI answers"
    assert "You are now Seen by AI on Gemini" in ch.sent[0].text_body


def test_brand_and_comparison_questions_never_count(db):
    client = _client(db)
    scans = None
    for category in ("brand", "comparison"):
        scans = _history(db, client, [(False, None), (True, 1), (True, 1)], category=category,
                         query=f"{category} question")
    assert process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),)) == []


def test_majority_of_samples_decides_and_unobserved_is_ignored(db):
    client = _client(db)
    _scan(db, client, 0, [("chatgpt", "recommendation", Q, False, None)])
    # 1 of 2 observed samples seen: not a majority, so not confirmed.
    _scan(db, client, 7, [
        ("chatgpt", "recommendation", Q, True, 1),
        ("chatgpt", "recommendation", Q, False, None),
        ("chatgpt", "recommendation", Q, False, None, None),  # unobserved
    ])
    s3 = _scan(db, client, 14, [("chatgpt", "recommendation", Q, True, 1)])
    assert process_client_wins(client.id, s3.id, db, channels=(FakeChannel(),)) == []


def test_baseline_with_no_stored_answer_does_not_count_as_not_seen(db):
    client = _client(db)
    _scan(db, client, 0, [("chatgpt", "recommendation", Q, False, None, None)])
    _scan(db, client, 7, [("chatgpt", "recommendation", Q, True, 1)])
    s3 = _scan(db, client, 14, [("chatgpt", "recommendation", Q, True, 1)])
    assert process_client_wins(client.id, s3.id, db, channels=(FakeChannel(),)) == []


def test_hallucination_flagged_rows_are_excluded(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    db.query(ScanQueryResult).filter(ScanQueryResult.scan_id == scans[1].id).update(
        {"hallucination_flagged": True}
    )
    db.commit()
    assert process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),)) == []


def test_score_formula_change_blocks_wins(db):
    client = _client(db)
    _scan(db, client, 0, [("chatgpt", "recommendation", Q, False, None)], version="v1.2.0")
    _scan(db, client, 7, [("chatgpt", "recommendation", Q, True, 1)])
    s3 = _scan(db, client, 14, [("chatgpt", "recommendation", Q, True, 1)])
    wins, _ = detect_wins(client.id, db)
    assert wins == []
    assert process_client_wins(client.id, s3.id, db, channels=(FakeChannel(),)) == []


def test_same_win_is_not_sent_twice(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    ch = FakeChannel()
    process_client_wins(client.id, scans[-1].id, db, channels=(ch,))
    # Redelivered post-commit step for the same scan.
    assert process_client_wins(client.id, scans[-1].id, db, channels=(ch,)) == []
    # Flaps out and back in within the renotify window.
    _scan(db, client, 21, [("chatgpt", "recommendation", Q, False, None)])
    _scan(db, client, 28, [("chatgpt", "recommendation", Q, True, 1)])
    s6 = _scan(db, client, 35, [("chatgpt", "recommendation", Q, True, 1)])
    assert process_client_wins(client.id, s6.id, db, channels=(ch,)) == []
    assert len(ch.sent) == 1


def test_disabled_client_records_but_never_sends(db):
    client = _client(db, enabled=False)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    ch = FakeChannel()
    rows = process_client_wins(client.id, scans[-1].id, db, channels=(ch,))
    assert [r.status for r in rows] == ["not_sent"]
    assert ch.sent == []
    # Turning it on later does not send the backlog.
    client.win_notifications_enabled = True
    db.commit()
    assert process_client_wins(client.id, scans[-1].id, db, channels=(ch,)) == []
    assert ch.sent == []


def test_prospect_never_notified(db):
    client = _client(db, is_prospect=True)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    ch = FakeChannel()
    rows = process_client_wins(client.id, scans[-1].id, db, channels=(ch,))
    assert [r.status for r in rows] == ["not_sent"]
    assert ch.sent == []


def test_only_latest_scan_triggers(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1), (True, 1)])
    assert process_client_wins(client.id, scans[2].id, db, channels=(FakeChannel(),)) == []


def test_failed_channel_marks_failed_and_alerts_admin(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    with patch("app.services.alert_service.send_email") as admin_email, \
         patch("app.services.alert_service.send_telegram"):
        rows = process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(fail=True),))
    assert [r.status for r in rows] == ["failed"]
    admin_email.assert_called_once()
    assert admin_email.call_args.kwargs["to"] != client.contact_email
    assert db.query(ActivityLog).filter(ActivityLog.event_type == "win_notification_failed").count() == 1


def test_one_channel_failing_does_not_block_another(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    good = FakeChannel("email")
    rows = process_client_wins(
        client.id, scans[-1].id, db, channels=(FakeChannel("other", fail=True), good)
    )
    assert rows[0].status == "sent" and rows[0].channels == "email"
    assert len(good.sent) == 1


def test_default_channels_email_only_and_whatsapp_never_available(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    assert WhatsAppChannel().is_available(client) is False
    with patch("app.services.notification_channels.send_email") as send:
        rows = process_client_wins(client.id, scans[-1].id, db)
    send.assert_called_once()
    assert send.call_args.kwargs["to"] == "owner@acme.example"
    assert rows[0].channels == "email"
    assert EmailChannel().is_available(Client(name="x", website="x", industry="x")) is False


def test_message_uses_approved_language(db):
    client = _client(db, share_token="tok123")
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    ch = FakeChannel()
    process_client_wins(client.id, scans[-1].id, db, channels=(ch,))
    msg = ch.sent[0]
    banned = r"\b(cited|uncited|mentioned|citation rate|ranking position|visibility gap|confidence|token|char offset)\b"
    for body in (msg.subject, msg.html_body, msg.text_body):
        assert not re.search(banned, body, re.IGNORECASE)
    assert "/view/tok123" in msg.html_body
    assert "SeenBy is a service of" in msg.text_body


def test_run_scan_wires_win_step_best_effort(db):
    """A crash in win processing must never undo a completed scan."""
    import inspect

    from app.services import scan_service

    src = inspect.getsource(scan_service.run_scan)
    assert "process_client_wins(client.id, scan.id, db)" in src
    block = src[src.index("process_client_wins"):]
    assert "db.rollback()" in block[:400]


def test_client_win_ids_are_uuid(db):
    client = _client(db)
    scans = _history(db, client, [(False, None), (True, 1), (True, 1)])
    process_client_wins(client.id, scans[-1].id, db, channels=(FakeChannel(),))
    win = db.query(ClientWin).one()
    assert isinstance(win.id, uuid.UUID)
    assert win.notified_at is not None
