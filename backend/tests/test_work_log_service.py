"""work_log_service — manual-first lifecycle (spec §3.2-3.3, §7)."""
from datetime import date, timedelta


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


# 1. Auto-suggestion idempotence: same source_ref twice → one row, updated.
def test_suggest_is_idempotent_and_updates(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    work_log_service.suggest(client.id, "technical", "First text", "toolkit_verified:llms", db)
    work_log_service.suggest(client.id, "technical", "Second text", "toolkit_verified:llms", db)
    rows = db.query(WorkLogEntry).all()
    assert len(rows) == 1
    assert rows[0].description == "Second text"
    assert rows[0].status == "suggested"


# 1b. Re-firing after publish/dismiss leaves the reviewed row untouched.
def test_suggest_never_regresses_published_or_dismissed(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.suggest(client.id, "technical", "Original", "ref:1", db)
    work_log_service.update_entry(entry, {"description": "Edited by admin", "status": "published"}, db)
    work_log_service.suggest(client.id, "technical", "Template text again", "ref:1", db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == "ref:1").one()
    assert row.description == "Edited by admin"
    assert row.status == "published"

    dismissed = work_log_service.suggest(client.id, "content", "D", "ref:2", db)
    work_log_service.update_entry(dismissed, {"status": "dismissed"}, db)
    work_log_service.suggest(client.id, "content", "D again", "ref:2", db)
    row2 = db.query(WorkLogEntry).filter(WorkLogEntry.source_ref == "ref:2").one()
    assert row2.status == "dismissed"


# 2. Sanitizer applied at write time.
def test_suggest_sanitizes_banned_language(db):
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.suggest(
        client.id, "visibility", "You are now cited by ChatGPT", "ref:san", db)
    assert "cited" not in entry.description
    assert "seen by AI" in entry.description


# 4. Manual entries are published immediately, no review step.
def test_create_manual_is_published_immediately(db):
    from app.services import work_log_service
    client = _make_client(db)
    entry = work_log_service.create_manual(
        client.id, "authority", "Submitted your business to three directories",
        date(2026, 7, 24), db)
    assert entry.status == "published"
    assert entry.published_at is not None
    assert entry.source == "manual"
    assert entry.source_ref is None


# 5. Status transitions.
def test_status_transitions(db):
    from app.services import work_log_service
    client = _make_client(db)
    e = work_log_service.suggest(client.id, "technical", "T", "ref:t", db)
    assert e.published_at is None
    work_log_service.update_entry(e, {"status": "published"}, db)
    assert e.status == "published" and e.published_at is not None
    work_log_service.update_entry(e, {"status": "dismissed"}, db)   # undo after publish
    assert e.status == "dismissed" and e.published_at is None


# 6. Editing a suggested row's description before publish persists the edit.
def test_edit_before_publish_persists(db):
    from app.services import work_log_service
    client = _make_client(db)
    e = work_log_service.suggest(client.id, "content", "Template", "ref:e", db)
    work_log_service.update_entry(e, {"description": "Faris's better wording"}, db)
    assert e.description == "Faris's better wording"


def test_published_entries_filters_status_and_window(db):
    from app.services import work_log_service
    client = _make_client(db)
    today = date(2026, 7, 24)
    inside = work_log_service.suggest(client.id, "technical", "Inside", "ref:in", db, entry_date=today)
    work_log_service.update_entry(inside, {"status": "published"}, db)
    outside = work_log_service.suggest(
        client.id, "technical", "Outside", "ref:out", db, entry_date=today - timedelta(days=60))
    work_log_service.update_entry(outside, {"status": "published"}, db)
    work_log_service.suggest(client.id, "technical", "Still suggested", "ref:sug", db, entry_date=today)

    published = work_log_service.published_entries(client.id, db, since=today - timedelta(days=30))
    descriptions = [p.description for p in published]
    assert "Inside" in descriptions
    assert "Outside" not in descriptions      # outside the window
    assert "Still suggested" not in descriptions  # not published
    assert work_log_service.published_count_since(client.id, db, today - timedelta(days=30)) == 1


def test_create_manual_rejects_unknown_category(db):
    import pytest
    from app.services import work_log_service
    client = _make_client(db)
    with pytest.raises(ValueError):
        work_log_service.create_manual(client.id, "bogus", "x", date(2026, 7, 24), db)
