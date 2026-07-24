"""Auto-suggest hooks (spec §3.3). Each writes a `suggested` row post-commit
and is best-effort — a failure must never undo the triggering operation."""
from unittest.mock import patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


# 3. A failure inside suggest() does not roll back the triggering commit.
def test_suggest_failure_does_not_undo_trigger(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service, work_log_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    with patch.object(work_log_service, "suggest", side_effect=Exception("boom")):
        # The status change must still commit even though the hook explodes.
        try:
            authority_service.update_asset(asset, {"status": "live"}, db)
        except Exception:
            db.rollback()
    db.expire_all()
    assert db.query(AuthorityAsset).one().status == "live"


def test_authority_live_writes_suggestion(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "authority").one()
    assert row.status == "suggested"
    assert row.source_ref == f"authority_live:{asset.id}"
    # Client-safe wording: no doubled "profile profile" noun, no raw enum.
    assert row.description == "Google Business Profile — now live"


def test_authority_missing_status_writes_nothing(db):
    from app.models.work_log_entry import WorkLogEntry
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "in_progress"}, db)
    assert db.query(WorkLogEntry).count() == 0


def test_authority_internal_only_key_writes_no_suggestion(db):
    """schema_sameas, wikipedia_readiness, media_mention carry internal
    checklist/schema jargon in their catalog name — never surfaced to the
    client work log even when the asset flips to live/verified."""
    from app.models.work_log_entry import WorkLogEntry
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "schema_sameas"}], db)
    authority_service.update_asset(asset, {"status": "live"}, db)
    assert db.query(WorkLogEntry).count() == 0


def test_remediation_corrected_writes_suggestion(db):
    from app.models.remediation_item import RemediationItem
    from app.models.work_log_entry import WorkLogEntry
    from app.services import remediation_service
    client = _make_client(db)
    item = RemediationItem(
        client_id=client.id, item_type="content_gap", platform="chatgpt",
        label="best dental clinic in KL", status="flagged",
    )
    db.add(item)
    db.commit()
    # NOTE: set_remediation_status takes item_id (uuid), not the item object —
    # see app/services/remediation_service.py:151 and its existing callers
    # (app/api/v1/remediation.py:64, tests/test_remediation_service.py:145).
    # The brief's snippet passed `item` directly; adapted to match the real
    # signature rather than inventing a new one.
    remediation_service.set_remediation_status(item.id, "corrected", db)
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "correction").one()
    assert row.source_ref == f"remediation:{item.id}"
    assert "best dental clinic in KL" in row.description


def test_remediation_auto_correction_writes_suggestion_and_dedupes_manual(db):
    """A scan-driven auto-correction (sync_remediation_items flipping an item
    to 'corrected' because it no longer appears) must write the same
    client-safe correction suggestion as the manual override — and the two
    paths must never double-write (shared source_ref, suggest() dedupes)."""
    from app.models.remediation_item import RemediationItem
    from app.models.work_log_entry import WorkLogEntry
    from app.services import remediation_service
    client = _make_client(db)
    item = RemediationItem(
        client_id=client.id, item_type="hallucination", platform="chatgpt",
        label="best dental clinic in KL", status="flagged",
    )
    db.add(item)
    db.commit()

    # No completed scan exists for this client, so the latest-scan lookups
    # inside sync_remediation_items find nothing "current" — the item reads
    # as absent from the latest scan and is auto-flipped to corrected.
    remediation_service.sync_remediation_items(client.id, db)
    db.expire_all()
    assert db.query(RemediationItem).filter(RemediationItem.id == item.id).one().status == "corrected"

    rows = db.query(WorkLogEntry).filter(WorkLogEntry.category == "correction").all()
    assert len(rows) == 1
    assert rows[0].status == "suggested"
    assert rows[0].source_ref == f"remediation:{item.id}"
    assert "best dental clinic in KL" in rows[0].description

    # Re-running sync must not re-suggest — the item was already corrected
    # before this run, so it's not among the newly-transitioned items.
    remediation_service.sync_remediation_items(client.id, db)
    assert db.query(WorkLogEntry).filter(WorkLogEntry.category == "correction").count() == 1

    # The manual admin path (set_remediation_status) shares the same
    # source_ref format — it must dedupe against the auto-written row rather
    # than creating a second correction entry.
    remediation_service.set_remediation_status(item.id, "corrected", db)
    assert db.query(WorkLogEntry).filter(WorkLogEntry.category == "correction").count() == 1


def test_query_flips_write_visibility_suggestions(db):
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    from app.models.work_log_entry import WorkLogEntry
    from app.services import work_log_service
    client = _make_client(db)
    older = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(older)
    db.commit()
    newer = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(newer)
    db.commit()
    for scan, detected in ((older, False), (newer, True)):
        db.add(ScanQueryResult(
            scan_id=scan.id, platform="chatgpt", category="recommendation",
            query_text="best dental clinic in KL", response_text="...",
            brand_detected=detected,
        ))
    db.commit()
    written = work_log_service.suggest_query_flips(client.id, db)
    assert written == 1
    row = db.query(WorkLogEntry).filter(WorkLogEntry.category == "visibility").one()
    assert "best dental clinic in KL" in row.description
    assert row.status == "suggested"
