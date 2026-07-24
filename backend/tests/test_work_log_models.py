"""WorkLogEntry persistence (spec §3.2)."""
from datetime import date


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_work_log_entry_defaults(db):
    from app.models.work_log_entry import WorkLogEntry
    client = _make_client(db)
    e = WorkLogEntry(
        client_id=client.id, category="technical",
        description="Published and verified llms.txt so AI systems can read your site",
        source="auto", source_ref="toolkit_verified:llms", entry_date=date(2026, 7, 24),
    )
    db.add(e)
    db.commit()
    row = db.query(WorkLogEntry).one()
    assert row.status == "suggested"
    assert row.published_at is None
    assert row.created_at is not None
    assert row.entry_date == date(2026, 7, 24)


def test_manual_entry_has_null_source_ref(db):
    from app.models.work_log_entry import WorkLogEntry
    client = _make_client(db)
    e = WorkLogEntry(
        client_id=client.id, category="authority",
        description="Submitted your business to three local directories",
        source="manual", source_ref=None, entry_date=date(2026, 7, 24),
        status="published",
    )
    db.add(e)
    db.commit()
    row = db.query(WorkLogEntry).one()
    assert row.source_ref is None
    assert row.status == "published"
