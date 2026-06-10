import uuid
from unittest.mock import MagicMock, patch

from workers.tasks.content_tasks import run_content_analysis


def _payload():
    return {
        "topics_json": [{"topic": "Solar Panels", "status": "strong"}],
        "entities_json": [{"entity": "Inverter", "covered": True}],
        "entity_coverage_score": 100.0,
        "content_metrics_json": {
            "word_count": 100,
            "h1_count": 1,
            "faq_count": 0,
            "blog_count": 0,
            "schema_present": False,
        },
        "content_quality_recommendation": "Add more pages.",
        "pages_crawled": 3,
    }


def test_run_content_analysis_marks_completed():
    client_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    analysis = MagicMock()
    analysis.id = analysis_id

    client = MagicMock()
    client.id = client_id

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [analysis, client]

    with patch("workers.tasks.content_tasks.SessionLocal", return_value=mock_db), patch(
        "workers.tasks.content_tasks.analyze_content", return_value=_payload()
    ):
        result = run_content_analysis(str(client_id), str(analysis_id))

    assert result["status"] == "completed"
    assert analysis.status == "completed"
    assert analysis.entity_coverage_score == 100.0
    assert analysis.pages_crawled == 3


def test_run_content_analysis_marks_failed_on_error():
    client_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    analysis = MagicMock()
    analysis.id = analysis_id

    client = MagicMock()
    client.id = client_id

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.side_effect = [analysis, client]

    with patch("workers.tasks.content_tasks.SessionLocal", return_value=mock_db), patch(
        "workers.tasks.content_tasks.analyze_content", side_effect=Exception("boom")
    ):
        result = run_content_analysis(str(client_id), str(analysis_id))

    assert result["status"] == "failed"
    assert analysis.status == "failed"


def test_run_content_analysis_handles_missing_row():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("workers.tasks.content_tasks.SessionLocal", return_value=mock_db):
        result = run_content_analysis(str(uuid.uuid4()), str(uuid.uuid4()))

    assert result["status"] == "not_found"
