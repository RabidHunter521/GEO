"""authority_service — catalog, CRUD (spec §4, §10). Real db fixture."""


def _make_client(db, industry="Dental clinic"):
    from app.models.client import Client
    c = Client(name="Acme Dental", website="https://acme.com",
               industry=industry, contact_email="hello@acme.com")
    db.add(c)
    db.commit()
    return c


def test_catalog_lists_all_items_unadded_for_new_client(db):
    from app.services import authority_service
    client = _make_client(db)
    catalog = authority_service.get_catalog(client, db)
    from app.core.constants import AUTHORITY_ASSET_CATALOG
    assert len(catalog) == len(AUTHORITY_ASSET_CATALOG)
    assert all(item["added"] is False for item in catalog)


def test_catalog_sorts_industry_matches_first(db):
    from app.services import authority_service
    client = _make_client(db, industry="Healthcare / dental clinic")
    catalog = authority_service.get_catalog(client, db)
    # myhealth_clinic (suggested_industries includes "dental"/"clinic") sorts
    # ahead of an item with no industry hint.
    keys = [i["key"] for i in catalog]
    assert keys.index("myhealth_clinic") < keys.index("linkedin")


def test_add_selected_catalog_keys_creates_exactly_those(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}, {"asset_key": "linkedin"}], db)
    rows = db.query(AuthorityAsset).filter(AuthorityAsset.client_id == client.id).all()
    assert {r.asset_key for r in rows} == {"gbp", "linkedin"}
    gbp = next(r for r in rows if r.asset_key == "gbp")
    assert gbp.name == "Google Business Profile"
    assert gbp.asset_type == "review_platform"
    assert gbp.provenance_domain == "google.com"
    assert gbp.status == "missing"


def test_add_is_idempotent_on_catalog_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    assert db.query(AuthorityAsset).filter(
        AuthorityAsset.client_id == client.id, AuthorityAsset.asset_key == "gbp"
    ).count() == 1


def test_add_custom_asset_has_null_key(db):
    from app.models.authority_asset import AuthorityAsset
    from app.services import authority_service
    client = _make_client(db)
    rows = authority_service.add_assets(
        client,
        [{"name": "Klinik directory XYZ", "asset_type": "directory",
          "url": "https://xyz.example/acme", "provenance_domain": "xyz.example"}],
        db,
    )
    assert len(rows) == 1
    row = db.query(AuthorityAsset).one()
    assert row.asset_key is None
    assert row.name == "Klinik directory XYZ"
    assert row.provenance_domain == "xyz.example"


def test_update_status_writes_activity_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "in_progress"}, db)
    log = db.query(ActivityLog).filter(
        ActivityLog.client_id == client.id,
        ActivityLog.event_type == "authority_status_changed",
    ).one()
    assert "in progress" in log.note.lower()
    assert asset.status == "in_progress"


def test_update_same_status_writes_no_log(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"url": "https://g.co/acme"}, db)  # no status change
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed"
    ).count() == 0
    assert asset.url == "https://g.co/acme"


def test_hidden_assets_excluded_by_default(db):
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"hidden": True}, db)
    assert authority_service.list_assets(client.id, db) == []
    assert len(authority_service.list_assets(client.id, db, include_hidden=True)) == 1


def test_update_ignores_invalid_status(db):
    from app.models.activity_log import ActivityLog
    from app.services import authority_service
    client = _make_client(db)
    (asset,) = authority_service.add_assets(client, [{"asset_key": "gbp"}], db)
    authority_service.update_asset(asset, {"status": "bogus"}, db)
    assert asset.status == "missing"  # unchanged — invalid status ignored
    assert db.query(ActivityLog).filter(
        ActivityLog.event_type == "authority_status_changed"
    ).count() == 0
