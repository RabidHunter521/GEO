# backend/tests/test_scan_service.py
import uuid
from unittest.mock import MagicMock, patch
from app.services.scan_service import run_scan


def make_scan(scan_id=None, client_id=None):
    scan = MagicMock()
    scan.id = scan_id or uuid.uuid4()
    scan.client_id = client_id or uuid.uuid4()
    scan.status = "pending"
    scan.platform = "gemini"
    return scan


def make_client(name="ACME Corp"):
    client = MagicMock()
    client.id = uuid.uuid4()
    client.name = name
    client.industry = "consulting"
    client.city = "Kuala Lumpur"
    client.state = "WP"
    client.brand_authority_score = 50
    client.content_quality_score = 50
    client.technical_foundations_verified = False
    client.structured_data_verified = False
    return client


def test_run_scan_sets_status_to_completed():
    scan = make_scan()
    client = make_client()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    mock_db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.return_value = "ACME Corp is great."
        MockGemini.return_value = mock_gemini
        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            with patch("app.services.scan_service.time.sleep"):
                run_scan(scan.id, mock_db)

    assert scan.status == "completed"


def test_run_scan_creates_geo_score_row():
    scan = make_scan()
    client = make_client()

    mock_db = MagicMock()
    # first.side_effect: scan lookup, client lookup
    mock_db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    # all() used for: competitors list, scan_query_results list
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [],   # competitors query
        [],   # scan_query_results query (for scoring)
    ]

    added_objects = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.return_value = "ACME Corp mentioned."
        MockGemini.return_value = mock_gemini
        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            with patch("app.services.scan_service.time.sleep"):
                run_scan(scan.id, mock_db)

    from app.models.geo_score import GeoScore
    geo_scores = [o for o in added_objects if isinstance(o, GeoScore)]
    assert len(geo_scores) == 1


def test_run_scan_sets_failed_on_gemini_error():
    scan = make_scan()
    client = make_client()

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [scan, client]
    mock_db.query.return_value.filter.return_value.all.return_value = []

    with patch("app.services.scan_service.GeminiClient") as MockGemini:
        mock_gemini = MagicMock()
        mock_gemini.query.side_effect = Exception("Gemini unavailable")
        MockGemini.return_value = mock_gemini
        with patch("app.services.scan_service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "fake"
            with patch("app.services.scan_service.time.sleep"):
                run_scan(scan.id, mock_db)

    assert scan.status == "failed"
