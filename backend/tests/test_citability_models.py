def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_page_audit_round_trip(db):
    from app.models.page_audit import PageAudit
    client = _make_client(db)
    audit = PageAudit(
        client_id=client.id,
        url="https://acme.com/services",
        score=72,
        checks=[{"id": "word_count", "label": "Page length", "status": "pass",
                 "detail": "About 800 words.", "points": 10}],
        suggestions=[{"section": "Intro", "issue": "Too long", "rewrite": "Shorter intro."}],
    )
    db.add(audit)
    db.commit()
    row = db.query(PageAudit).one()
    assert row.score == 72
    assert row.checks[0]["id"] == "word_count"
    assert row.suggestions[0]["section"] == "Intro"
    assert row.suggestions_failed is False
    assert row.created_at is not None


def test_content_deliverable_defaults(db):
    from app.models.content_deliverable import ContentDeliverable
    client = _make_client(db)
    d = ContentDeliverable(
        client_id=client.id, type="faq_pack",
        title="FAQ pack", body_md="# FAQ\n...", source_context={"scan_id": None},
    )
    db.add(d)
    db.commit()
    row = db.query(ContentDeliverable).one()
    assert row.status == "draft"
    assert row.competitor_id is None
    assert row.reviewed_at is None
    assert row.generated_at is not None
