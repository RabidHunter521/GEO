import uuid
import pytest
from unittest.mock import MagicMock, patch

from app.models.scan_query_result import ScanQueryResult
from app.models.scan import Scan
from app.models.client import Client


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(name="Test Brand", threshold=35):
    c = MagicMock(spec=Client)
    c.id = uuid.uuid4()
    c.name = name
    c.industry = "Technology"
    c.score_drop_threshold = threshold
    return c


def _make_geo_score(overall_score: float):
    gs = MagicMock()
    gs.overall_score = overall_score
    return gs


# ── check_score_drop_alert ────────────────────────────────────────────────────

def test_score_drop_fires_when_crosses_below_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(30.0), _make_geo_score(40.0), db)
    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "contact@seenby.my" == kwargs["to"]
    assert "Test Brand" in kwargs["subject"]
    assert "Growth Readiness" in kwargs["subject"]
    assert "GEO Score" not in kwargs["subject"]
    assert "Growth Readiness" in kwargs["html_body"]
    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "alert_sent"
    assert "35" in added.note


def test_score_drop_does_not_fire_when_already_below_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        # prev=30, current=25 — both below threshold, no crossing
        check_score_drop_alert(client, _make_geo_score(25.0), _make_geo_score(30.0), db)
    mock_send.assert_not_called()
    db.commit.assert_not_called()


def test_score_drop_does_not_fire_when_both_above_threshold():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(40.0), _make_geo_score(50.0), db)
    mock_send.assert_not_called()


def test_score_drop_does_not_fire_on_first_scan():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        check_score_drop_alert(client, _make_geo_score(20.0), None, db)
    mock_send.assert_not_called()


def test_score_drop_fires_at_exact_threshold_boundary():
    from app.services.alert_service import check_score_drop_alert
    client = _make_client(threshold=35)
    db = MagicMock()
    with patch("app.services.alert_service.send_email") as mock_send:
        # prev=35 (at threshold = was_above), current=34.9 (now_below)
        check_score_drop_alert(client, _make_geo_score(34.9), _make_geo_score(35.0), db)
    mock_send.assert_called_once()


# ── check_competitor_overtake_alert ──────────────────────────────────────────
# Head-to-head on the SAME answers: the client's own discovery questions.
# A competitor is "seen" in an answer when the answer text names it.

def _overtake_setup(db, competitors=(("Rival Corp", ()),)):
    from app.models.competitor import Competitor
    from app.models.scan import Scan as ScanModel
    from app.core.time import utcnow

    client = Client(name="Test Brand", website="https://test.my", industry="payment gateway")
    db.add(client)
    db.commit()
    comps = []
    for name, aliases in competitors:
        comp = Competitor(client_id=client.id, name=name, brand_aliases=list(aliases))
        db.add(comp)
        comps.append(comp)
    scan = ScanModel(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    return client, comps, scan


def _answer(db, scan, text, client_seen, platform="chatgpt", category="recommendation",
            competitor_id=None):
    db.add(ScanQueryResult(
        scan_id=scan.id, platform=platform, category=category, competitor_id=competitor_id,
        query_text=f"q{uuid.uuid4().hex[:6]}", response_text=text, brand_detected=client_seen,
    ))
    db.commit()


def test_competitor_overtake_fires_when_competitor_shows_in_more_of_the_same_answers(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db)
    _answer(db, scan, "Try Test Brand or Rival Corp.", True)
    _answer(db, scan, "Rival Corp is the top pick.", False)
    _answer(db, scan, "Rival Corp and Stripe lead here.", False)
    _answer(db, scan, "Stripe is popular.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "Rival Corp" in kwargs["html_body"]
    assert "contact@seenby.my" == kwargs["to"]


def test_competitor_overtake_does_not_fire_when_client_ahead(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db)
    _answer(db, scan, "Test Brand is great.", True)
    _answer(db, scan, "Test Brand or Rival Corp.", True)
    _answer(db, scan, "Stripe is popular.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_not_called()


def test_competitor_overtake_ignores_questions_that_name_a_brand(db):
    """The old bias: the competitor's own "Tell me about Rival Corp" rows and
    the client's brand/comparison rows decided the alert. Neither brand shows
    on the neutral questions here, so nobody is ahead."""
    from app.services.alert_service import check_competitor_overtake_alert
    client, (rival,), scan = _overtake_setup(db)
    _answer(db, scan, "Test Brand is a payment gateway.", True, category="brand")
    _answer(db, scan, "Test Brand vs Rival Corp: both fine.", True, category="comparison")
    _answer(db, scan, "Rival Corp is a payment gateway.", True, category="brand",
            competitor_id=rival.id)
    _answer(db, scan, "Rival Corp vs Test Brand.", True, category="comparison",
            competitor_id=rival.id)
    _answer(db, scan, "Stripe and Billplz are popular.", False)
    _answer(db, scan, "Stripe leads.", False, category="local")

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_not_called()


def test_competitor_overtake_does_not_repeat_when_already_ahead_last_scan(db):
    from app.models.scan import Scan as ScanModel
    from app.services.alert_service import check_competitor_overtake_alert
    from datetime import timedelta
    from app.core.time import utcnow

    client, _, scan = _overtake_setup(db)
    previous = ScanModel(client_id=client.id, status="completed",
                         completed_at=utcnow() - timedelta(days=7))
    db.add(previous)
    db.commit()
    _answer(db, previous, "Rival Corp is the top pick.", False)
    _answer(db, scan, "Rival Corp is the top pick.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_not_called()


def test_competitor_overtake_fires_when_previous_answers_were_purged(db):
    from app.models.scan import Scan as ScanModel
    from app.services.alert_service import check_competitor_overtake_alert
    from datetime import timedelta
    from app.core.time import utcnow

    client, _, scan = _overtake_setup(db)
    previous = ScanModel(client_id=client.id, status="completed",
                         completed_at=utcnow() - timedelta(days=100))
    db.add(previous)
    db.commit()
    _answer(db, previous, None, False)  # raw text purged after 90 days
    _answer(db, scan, "Rival Corp is the top pick.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_called_once()


def test_competitor_overtake_recognises_competitor_aliases(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db, competitors=(("Fiuu", ("Razer Merchant Services",)),))
    _answer(db, scan, "Razer Merchant Services is widely used.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_called_once()
    assert "Fiuu" in mock_send.call_args[1]["html_body"]


def test_competitor_overtake_does_not_fire_when_no_competitors(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client = Client(name="Lonely", website="https://l.my", industry="x")
    db.add(client)
    db.commit()

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, uuid.uuid4(), db)

    mock_send.assert_not_called()


def test_competitor_overtake_fires_once_per_winning_competitor(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db, competitors=(("Alpha", ()), ("Beta", ())))
    _answer(db, scan, "Alpha and Test Brand.", True)
    _answer(db, scan, "Alpha is best.", False)
    _answer(db, scan, "Beta is fine.", False)
    _answer(db, scan, "Nobody relevant.", False)

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    assert mock_send.call_count == 1
    assert "Alpha" in mock_send.call_args[1]["html_body"]


def test_competitor_overtake_email_lists_winning_platforms_and_ignores_google(db):
    from app.models.activity_log import ActivityLog
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db)
    # Gemini: client 2/2, rival 1/2. ChatGPT: client 0/2, rival 2/2.
    _answer(db, scan, "Test Brand and Rival Corp.", True, platform="gemini")
    _answer(db, scan, "Test Brand.", True, platform="gemini")
    _answer(db, scan, "Rival Corp.", False, platform="chatgpt")
    _answer(db, scan, "Rival Corp again.", False, platform="chatgpt")
    # Reported-only surface: must not move the comparison either way.
    for _ in range(4):
        _answer(db, scan, "Rival Corp.", False, platform="google_aio")

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_called_once()
    body = mock_send.call_args[1]["html_body"]
    assert "Platforms where Rival Corp is ahead" in body
    section = body.split("Platforms where")[1]
    assert "ChatGPT" in section
    assert "Gemini" not in section
    assert "Google" not in section
    note = db.query(ActivityLog).filter(ActivityLog.event_type == "alert_sent").one().note
    assert "Ahead on: ChatGPT." in note
    assert "same 4 discovery answers" in note


def test_competitor_overtake_platform_lead_alone_does_not_fire(db):
    from app.services.alert_service import check_competitor_overtake_alert
    client, _, scan = _overtake_setup(db)
    # Client 3/4 overall; rival 2/4 overall but ahead on ChatGPT.
    _answer(db, scan, "Test Brand.", True, platform="gemini")
    _answer(db, scan, "Test Brand.", True, platform="gemini")
    _answer(db, scan, "Test Brand and Rival Corp.", True, platform="chatgpt")
    _answer(db, scan, "Rival Corp.", False, platform="chatgpt")

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan.id, db)

    mock_send.assert_not_called()


# ── flag_hallucination ────────────────────────────────────────────────────────

def test_flag_hallucination_sends_email_and_logs_activity():
    from app.services.alert_service import flag_hallucination

    result_id = uuid.uuid4()
    mock_result = MagicMock(spec=ScanQueryResult)
    mock_result.id = result_id
    mock_result.scan_id = uuid.uuid4()
    mock_result.query_text = "What is Test Brand known for?"
    mock_result.response_text = "Test Brand has no presence in the market."

    mock_scan = MagicMock(spec=Scan)
    mock_scan.client_id = uuid.uuid4()

    mock_client = MagicMock(spec=Client)
    mock_client.id = mock_scan.client_id
    mock_client.name = "Test Brand"

    db = MagicMock()
    db.get.side_effect = lambda model, val: {
        ScanQueryResult: mock_result,
        Scan: mock_scan,
        Client: mock_client,
    }[model]

    with patch("app.services.alert_service.send_email") as mock_send:
        flag_hallucination(result_id, db)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "contact@seenby.my" == kwargs["to"]
    assert "Test Brand" in kwargs["subject"]
    assert "What is Test Brand known for?" in kwargs["html_body"]

    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.event_type == "hallucination_flagged"
    assert added.client_id == mock_client.id


def test_flag_hallucination_raises_when_result_not_found():
    from app.services.alert_service import flag_hallucination
    db = MagicMock()
    db.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        flag_hallucination(uuid.uuid4(), db)
