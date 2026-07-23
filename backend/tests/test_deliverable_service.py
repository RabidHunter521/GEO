"""deliverable_service tests — mocked Anthropic, real db fixture (spec §8)."""
from unittest.mock import MagicMock, patch


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def _make_scan_with_results(db, client, n_lost=3):
    from app.core.time import utcnow
    from app.models.scan import Scan
    from app.models.scan_query_result import ScanQueryResult
    scan = Scan(client_id=client.id, status="completed", completed_at=utcnow())
    db.add(scan)
    db.commit()
    for i in range(n_lost):
        db.add(ScanQueryResult(
            scan_id=scan.id, platform="chatgpt", category="recommendation",
            query_text=f"best dental clinic in KL {i}",
            response_text="Some answer text naming Rival Dental.",
            brand_detected=False,
        ))
    db.commit()
    return scan


def _mock_anthropic(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    ac = MagicMock()
    ac.messages.create.return_value = resp
    return ac


_ENVELOPE = '{"title": "Dental FAQ Pack", "body_md": "# FAQ\\n\\n**Q:** How much?\\n**A:** RM 120."}'


def test_faq_pack_generates_and_persists_draft(db):
    from app.models.activity_log import ActivityLog
    from app.services import deliverable_service
    client = _make_client(db)
    scan = _make_scan_with_results(db, client)
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "faq_pack", db)
    assert d is not None
    assert d.status == "draft"
    assert d.title == "Dental FAQ Pack"
    assert d.body_md.startswith("# FAQ")
    assert d.source_context["scan_id"] == str(scan.id)
    log = db.query(ActivityLog).filter(ActivityLog.client_id == client.id).one()
    assert log.event_type == "deliverable_generated"


def test_comparison_page_requires_competitor(db):
    import pytest
    from app.services import deliverable_service
    client = _make_client(db)
    with pytest.raises(ValueError):
        deliverable_service.generate_deliverable(client, "comparison_page", db, competitor=None)


def test_comparison_page_generates_with_competitor(db):
    from app.models.competitor import Competitor
    from app.services import deliverable_service
    client = _make_client(db)
    _make_scan_with_results(db, client)
    comp = Competitor(client_id=client.id, name="Rival Dental", website="https://rival.com")
    db.add(comp)
    db.commit()
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "comparison_page", db, competitor=comp)
    assert d is not None
    assert d.competitor_id == comp.id


def test_glossary_generates_without_scan(db):
    from app.services import deliverable_service
    client = _make_client(db)  # no scan at all — profile-only evidence is fine
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d is not None
    assert d.type == "glossary"


def test_claude_failure_persists_nothing(db):
    from app.models.content_deliverable import ContentDeliverable
    from app.services import deliverable_service
    client = _make_client(db)
    with patch.object(deliverable_service, "anthropic_client", side_effect=Exception("down")):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d is None
    assert db.query(ContentDeliverable).count() == 0


def test_banned_language_sanitized_in_body(db):
    from app.services import deliverable_service
    client = _make_client(db)
    dirty = '{"title": "Why Acme is cited", "body_md": "Acme is cited and mentioned often."}'
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(dirty)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert "cited" not in d.body_md
    assert "mentioned" not in d.body_md
    assert "seen by AI" in d.body_md
    assert "cited" not in d.title


def test_regenerate_never_touches_reviewed_row(db):
    from app.core.time import utcnow
    from app.models.content_deliverable import ContentDeliverable
    from app.services import deliverable_service
    client = _make_client(db)
    reviewed = ContentDeliverable(
        client_id=client.id, type="glossary", title="Reviewed glossary",
        body_md="approved text", status="reviewed", reviewed_at=utcnow(),
    )
    db.add(reviewed)
    db.commit()
    with patch.object(deliverable_service, "anthropic_client",
                      return_value=_mock_anthropic(_ENVELOPE)), \
         patch.object(deliverable_service, "record_llm_call"):
        d = deliverable_service.generate_deliverable(client, "glossary", db)
    assert d.id != reviewed.id
    db.refresh(reviewed)
    assert reviewed.body_md == "approved text"
    assert reviewed.status == "reviewed"
    assert db.query(ContentDeliverable).count() == 2
