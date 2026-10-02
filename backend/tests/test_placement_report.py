"""Placement engine Task 8: won placements in the monthly PDF, and only those."""
from datetime import timedelta

from app.core.time import utcnow
from app.models.work_log_entry import WorkLogEntry
from app.services import outcome_verification_service, report_service, work_log_service
from app.services import placement_service as ps
from tests.test_placement_lifecycle import _answer, _discovered, _publish, _scan, _QUERY
from tests.test_report_v2 import BANNED_TERMS, _minimal_data

_STUB_CLIENT = type("C", (), {"name": "Acme", "website": "https://acme.com", "industry": "Dental"})()


def _since():
    return utcnow() - timedelta(days=30)


def _placed(db, *, flipped=False):
    """Discovered -> pursued -> published -> a later scan finds the client on
    the page (and, when flipped, the proof question now sees them too)."""
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)
    later = _scan(db, client, 5)
    _answer(db, later, seen=flipped, client_on_page=True)
    outcome_verification_service.verify_waiting_actions(later.id, client.id, db)
    ps.refresh_targets(later.id, client.id, db)
    db.refresh(t)
    return client, t, action


def _publish_entry(db, client, source_ref):
    entry = db.query(WorkLogEntry).filter_by(client_id=client.id, source_ref=source_ref).one()
    work_log_service.update_entry(entry, {"status": "published"}, db)
    return entry


def test_published_placement_is_reported(db):
    client, t, _ = _placed(db)
    _publish_entry(db, client, f"placement:{t.id}:placed")

    lines = report_service._gather_placements_secured(client, db, _since(), utcnow())

    assert [line.text for line in lines] == [
        "Now listed on klguide.example, a page an AI answer drew on for your buyer questions."
    ]
    assert lines[0].verified is False


def test_unpublished_placement_stays_off_the_report(db):
    client, _, _ = _placed(db)  # suggested, never published by an admin

    assert report_service._gather_placements_secured(client, db, _since(), utcnow()) == []


def test_in_flight_outreach_never_reaches_the_report(db):
    client, t, _ = _discovered(db)
    action = ps.pursue(t, db)
    _publish(db, action, day=2)

    assert report_service._gather_placements_secured(client, db, _since(), utcnow()) == []


def test_placement_published_in_an_earlier_period_is_not_reprinted(db):
    client, t, _ = _placed(db)
    entry = _publish_entry(db, client, f"placement:{t.id}:placed")
    entry.published_at = utcnow() - timedelta(days=60)
    db.commit()

    assert report_service._gather_placements_secured(client, db, _since(), utcnow()) == []


def test_verified_placement_names_the_question_ai_now_answers_with_the_client(db):
    client, t, action = _placed(db, flipped=True)
    assert t.status == "verified"
    _publish_entry(db, client, f"placement:{t.id}:placed")
    _publish_entry(db, client, f"outcome_action:{action.id}")

    [line] = report_service._gather_placements_secured(client, db, _since(), utcnow())

    assert line.verified is True
    assert line.text.endswith(f'AI now sees you when asked "{_QUERY}".')


def test_verification_is_not_claimed_until_its_entry_is_published(db):
    client, t, _ = _placed(db, flipped=True)
    _publish_entry(db, client, f"placement:{t.id}:placed")  # verified entry left unpublished

    [line] = report_service._gather_placements_secured(client, db, _since(), utcnow())

    assert line.verified is False
    assert "AI now sees you" not in line.text


def test_section_absent_when_empty_and_clean_when_present():
    empty = report_service._build_report_html(_STUB_CLIENT, _minimal_data())
    assert "Placements Secured" not in empty

    data = _minimal_data(placements_secured=[report_service.PlacementLine(
        domain="klguide.example",
        text=f'Now listed on klguide.example, a page AI answers drew on 4 times for your '
             f'buyer questions. AI now sees you when asked "{_QUERY}".',
        verified=True,
    )])
    html = report_service._build_report_html(_STUB_CLIENT, data)
    assert "Placements Secured" in html
    assert "drew on 4 times" in html
    section = html[html.index("Placements Secured"):].split("<h2>", 1)[0].lower()
    for term in BANNED_TERMS:
        assert term not in section
