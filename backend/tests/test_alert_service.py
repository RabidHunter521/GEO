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

def _make_results(n_detected: int, n_total: int, competitor_id=None, platform="gemini"):
    results = []
    for i in range(n_total):
        r = MagicMock()
        r.competitor_id = competitor_id
        r.brand_detected = i < n_detected
        r.platform = platform
        results.append(r)
    return results


def test_competitor_overtake_fires_when_competitor_ahead():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id = uuid.uuid4()

    competitor = MagicMock()
    competitor.id = comp_id
    competitor.name = "Rival Corp"

    client_results = _make_results(2, 8, competitor_id=None)   # 25%
    comp_results = _make_results(3, 4, competitor_id=comp_id)  # 75%

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    mock_send.assert_called_once()
    kwargs = mock_send.call_args[1]
    assert "Rival Corp" in kwargs["html_body"]
    assert "contact@seenby.my" == kwargs["to"]
    db.commit.assert_called_once()


def test_competitor_overtake_does_not_fire_when_client_ahead():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id = uuid.uuid4()

    competitor = MagicMock()
    competitor.id = comp_id
    competitor.name = "Small Rival"

    client_results = _make_results(6, 8, competitor_id=None)   # 75%
    comp_results = _make_results(1, 4, competitor_id=comp_id)  # 25%

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    mock_send.assert_not_called()
    db.commit.assert_not_called()


def test_competitor_overtake_does_not_fire_when_no_competitors():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, uuid.uuid4(), db)

    mock_send.assert_not_called()


def test_competitor_overtake_fires_once_per_winning_competitor():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id_a, comp_id_b = uuid.uuid4(), uuid.uuid4()

    comp_a = MagicMock(); comp_a.id = comp_id_a; comp_a.name = "Alpha"
    comp_b = MagicMock(); comp_b.id = comp_id_b; comp_b.name = "Beta"

    client_results = _make_results(2, 8, competitor_id=None)       # 25%
    comp_a_results = _make_results(3, 4, competitor_id=comp_id_a)  # 75% — wins
    comp_b_results = _make_results(1, 4, competitor_id=comp_id_b)  # 25% — tie (not > client)

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [comp_a, comp_b],
        client_results + comp_a_results + comp_b_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    assert mock_send.call_count == 1
    kwargs = mock_send.call_args[1]
    assert "Alpha" in kwargs["html_body"]


def test_competitor_overtake_email_lists_winning_platforms():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    scan_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    competitor = MagicMock(); competitor.id = comp_id; competitor.name = "Rival Corp"

    # Client: gemini 100% (2/2), chatgpt 0% (0/2) → overall 50%
    client_results = (
        _make_results(2, 2, competitor_id=None, platform="gemini")
        + _make_results(0, 2, competitor_id=None, platform="chatgpt")
    )
    # Competitor: gemini 50% (1/2), chatgpt 100% (2/2) → overall 75% (fires)
    comp_results = (
        _make_results(1, 2, competitor_id=comp_id, platform="gemini")
        + _make_results(2, 2, competitor_id=comp_id, platform="chatgpt")
    )

    db = MagicMock()
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, scan_id, db)

    mock_send.assert_called_once()
    body = mock_send.call_args[1]["html_body"]
    assert "Platforms where Rival Corp is ahead" in body
    assert "ChatGPT" in body
    assert "Gemini" not in body.split("Platforms where")[1]  # client ahead on Gemini
    # ActivityLog note carries platform detail
    notes = [o.note for o in added if hasattr(o, "note")]
    assert any("Ahead on: ChatGPT." in str(n) for n in notes)


def test_competitor_overtake_platform_lead_alone_does_not_fire():
    from app.services.alert_service import check_competitor_overtake_alert
    client = _make_client()
    comp_id = uuid.uuid4()
    competitor = MagicMock(); competitor.id = comp_id; competitor.name = "Rival Corp"

    # Client overall 62.5% (gemini 4/4, chatgpt 1/4)
    client_results = (
        _make_results(4, 4, competitor_id=None, platform="gemini")
        + _make_results(1, 4, competitor_id=None, platform="chatgpt")
    )
    # Competitor overall 50% but 100% on chatgpt — must NOT fire
    comp_results = (
        _make_results(0, 2, competitor_id=comp_id, platform="gemini")
        + _make_results(2, 2, competitor_id=comp_id, platform="chatgpt")
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.all.side_effect = [
        [competitor],
        client_results + comp_results,
    ]

    with patch("app.services.alert_service.send_email") as mock_send:
        check_competitor_overtake_alert(client, uuid.uuid4(), db)

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
