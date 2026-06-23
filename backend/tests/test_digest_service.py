import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services.digest_service import DigestData, _compute_trend, _detect_first_seen


# ── _compute_trend ────────────────────────────────────────────────────────────

def test_trend_up_when_current_exceeds_prev_by_more_than_half_point():
    assert _compute_trend(70.0, 60.0) == "up"


def test_trend_down_when_current_below_prev_by_more_than_half_point():
    assert _compute_trend(55.0, 70.0) == "down"


def test_trend_flat_when_change_is_within_half_point():
    assert _compute_trend(60.3, 60.0) == "flat"


def test_trend_first_when_no_previous_scan():
    assert _compute_trend(50.0, None) == "first"


# ── _detect_first_seen ────────────────────────────────────────────────────────

def test_first_seen_false_when_seen_count_is_zero():
    db = MagicMock()
    assert _detect_first_seen(seen_count=0, prev_scan=None, db=db) is False


def test_first_seen_true_when_seen_and_no_previous_scan():
    db = MagicMock()
    assert _detect_first_seen(seen_count=3, prev_scan=None, db=db) is True


def test_first_seen_true_when_prev_scan_had_zero_detections():
    prev_scan = MagicMock()
    prev_scan.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 0
    assert _detect_first_seen(seen_count=2, prev_scan=prev_scan, db=db) is True


def test_first_seen_false_when_prev_scan_also_had_detections():
    prev_scan = MagicMock()
    prev_scan.id = uuid.uuid4()
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = 5
    assert _detect_first_seen(seen_count=4, prev_scan=prev_scan, db=db) is False


# ── send_client_digest ────────────────────────────────────────────────────────

def _make_client(contact_email="client@example.com", archived=False):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.name = "Test Brand"
    c.industry = "Technology"
    c.contact_email = contact_email
    c.archived_at = datetime.utcnow() if archived else None
    c.is_prospect = False
    return c


def _make_digest_data():
    return DigestData(
        seen_count=5,
        total_count=8,
        current_ai_citability=62.5,
        current_overall_score=60.0,
        prev_ai_citability=50.0,
        trend="up",
        is_first_seen=False,
        action_text="Publish a blog post featuring your brand name.",
    )


def test_send_client_digest_skips_archived_client():
    db = MagicMock()
    db.get.return_value = _make_client(archived=True)
    from app.services.digest_service import send_client_digest
    assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_skips_client_without_contact_email():
    db = MagicMock()
    db.get.return_value = _make_client(contact_email=None)
    from app.services.digest_service import send_client_digest
    assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_skips_when_no_scan_this_week():
    db = MagicMock()
    db.get.return_value = _make_client()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=None):
        assert send_client_digest(uuid.uuid4(), db) is False


def test_send_client_digest_sends_email_and_returns_true():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None  # no recent digest
    data = _make_digest_data()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email") as mock_send:
        result = send_client_digest(client.id, db)
    assert result is True
    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert kwargs["to"] == "client@example.com"
    assert "60" in kwargs["subject"]
    assert "Test Brand" in kwargs["subject"]


def test_send_client_digest_writes_digest_sent_activity_log_entry():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None  # no recent digest
    data = _make_digest_data()
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email"):
        send_client_digest(client.id, db)
    db.add.assert_called()
    db.commit.assert_called()
    added_obj = db.add.call_args[0][0]
    assert added_obj.event_type == "digest_sent"
    assert "client@example.com" in added_obj.note


def test_subject_leads_with_seen_count_and_keeps_score():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data()  # seen 5/8, score 60
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    subject = captured["subject"]
    assert "5/8" in subject          # leads with the human result
    assert "60" in subject           # CLAUDE.md §7 — score stays in the subject
    assert "Test Brand" in subject


def test_email_html_includes_verbatim_proof_quote():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data()
    data.proof_quote = "Acme is a top choice for enterprise teams."
    data.proof_platform = "ChatGPT"
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    html = captured["html_body"]
    assert "Acme is a top choice for enterprise teams." in html
    assert "Straight from ChatGPT" in html


def test_email_html_omits_proof_block_when_no_quote():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None
    data = _make_digest_data()  # proof_quote defaults to None
    captured = {}
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=lambda **k: captured.update(k)):
        send_client_digest(client.id, db)
    assert "Straight from" not in captured["html_body"]


def test_email_html_contains_seen_count_and_trend_message():
    db = MagicMock()
    client = _make_client()
    db.get.return_value = client
    db.query.return_value.filter.return_value.first.return_value = None  # no recent digest
    data = _make_digest_data()  # trend="up", seen_count=5, total_count=8
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
    from app.services.digest_service import send_client_digest
    with patch("app.services.digest_service._compute_digest_data", return_value=data), \
         patch("app.services.digest_service.send_email", side_effect=capture):
        send_client_digest(client.id, db)
    html = captured["html_body"]
    assert "5/8" in html
    assert "improved" in html  # trend "up" → "Your AI visibility improved"
