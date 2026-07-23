"""AuthorityAsset + Client.phone persistence (spec §3)."""


def _make_client(db):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry="Dental clinic", contact_email="hello@acme.com",
               phone="+60 3-1234 5678")
    db.add(c)
    db.commit()
    return c


def test_client_phone_round_trip(db):
    from app.models.client import Client
    client = _make_client(db)
    assert db.query(Client).one().phone == "+60 3-1234 5678"


def test_authority_asset_defaults(db):
    from app.models.authority_asset import AuthorityAsset
    client = _make_client(db)
    a = AuthorityAsset(
        client_id=client.id, asset_key="gbp", name="Google Business Profile",
        asset_type="review_platform", provenance_domain="google.com",
    )
    db.add(a)
    db.commit()
    row = db.query(AuthorityAsset).one()
    assert row.status == "missing"
    assert row.hidden is False
    assert row.nap_mismatch is False
    assert row.review_snapshots == []
    assert row.found_nap is None
    assert row.url is None
    assert row.last_checked_at is None
    assert row.created_at is not None


def test_authority_asset_custom_has_null_key(db):
    from app.models.authority_asset import AuthorityAsset
    client = _make_client(db)
    a = AuthorityAsset(client_id=client.id, asset_key=None,
                       name="Some niche directory", asset_type="directory")
    db.add(a)
    db.commit()
    assert db.query(AuthorityAsset).one().asset_key is None
