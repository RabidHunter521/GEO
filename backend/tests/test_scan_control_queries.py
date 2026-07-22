import uuid
from unittest.mock import MagicMock, patch

from app.core.constants import MAX_CONTROL_QUERIES
from app.models.client import Client
from app.models.control_query import ControlQuery
from app.models.scan import Scan
from app.services import scan_service
from app.services.query_builder import build_control_queries
from app.services.scan_service import _run_platform_queries


def test_build_control_queries_shape_and_cap():
    controls = [
        ControlQuery(client_id=uuid.uuid4(), query_text=f"q{i}", category="recommendation", active=True)
        for i in range(7)
    ]
    built = build_control_queries(controls)
    assert len(built) == MAX_CONTROL_QUERIES  # capped defensively
    assert all(q["is_control"] for q in built)
    assert built[0]["competitor_id"] is None


def test_build_control_queries_skips_inactive():
    controls = [
        ControlQuery(client_id=uuid.uuid4(), query_text="active q", category="recommendation", active=True),
        ControlQuery(client_id=uuid.uuid4(), query_text="inactive q", category="recommendation", active=False),
    ]
    built = build_control_queries(controls)
    assert [q["query_text"] for q in built] == ["active q"]


def test_platform_run_marks_control_rows(db):
    client = Client(name="Clinic A", website="https://a.my", industry="dental clinic", city="KL")
    db.add(client)
    db.commit()
    scan = Scan(client_id=client.id)
    db.add(scan)
    db.commit()
    controls = [ControlQuery(client_id=client.id, query_text="Best physio in Penang",
                             category="recommendation", active=True)]
    pc = MagicMock()
    pc.query.return_value = MagicMock(text="Some answer", citations=[], model="m",
                                      input_tokens=1, output_tokens=1)
    with patch.object(scan_service, "_INTER_QUERY_DELAY_SECONDS", 0):
        results, _ = _run_platform_queries("chatgpt", pc, scan, client, [], controls)
    control_rows = [r for r in results if r.is_control]
    assert len(control_rows) == 1
    assert control_rows[0].query_text == "Best physio in Penang"
    assert all(not r.is_control for r in results if r.query_text != "Best physio in Penang")
