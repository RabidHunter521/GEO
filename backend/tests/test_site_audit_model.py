import uuid


def _make_client(db):
    from app.models.client import Client
    c = Client(
        name="Acme Dental",
        website="https://acme.com",
        industry="Dental clinic",
        contact_email="hello@acme.com",
    )
    db.add(c)
    db.commit()
    return c


def test_site_audit_round_trip(db):
    from app.models.site_audit import SiteAudit
    client = _make_client(db)
    checks = [
        {"id": "https", "label": "Secure connection (HTTPS)", "status": "pass",
         "detail": "Your site is served over a secure connection.", "fix": ""},
    ]
    audit = SiteAudit(client_id=client.id, checks=checks, passed=1, warned=0, failed=0, unknown=0)
    db.add(audit)
    db.commit()

    row = db.query(SiteAudit).one()
    assert row.client_id == client.id
    assert row.checks[0]["id"] == "https"
    assert (row.passed, row.warned, row.failed, row.unknown) == (1, 0, 0, 0)
    assert row.created_at is not None


def test_toolkit_files_llms_full_columns_default(db):
    from app.models.toolkit_files import ToolkitFiles
    client = _make_client(db)
    tf = ToolkitFiles(client_id=client.id, llms_txt="x", schema_json="{}", robots_txt="y")
    db.add(tf)
    db.commit()
    row = db.query(ToolkitFiles).one()
    assert row.llms_full_txt is None
    assert row.llms_full_verified is False
