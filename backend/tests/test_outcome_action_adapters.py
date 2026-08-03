"""Idempotent adapters connecting specialist evidence to Outcome Actions."""
from app.models.action_recommendation import ActionRecommendation
from app.models.authority_asset import AuthorityAsset
from app.models.content_deliverable import ContentDeliverable
from app.models.outcome_action import OutcomeAction
from app.models.remediation_item import RemediationItem
from app.services import outcome_action_adapter_service as adapters


def _make_client(db):
    from app.models.client import Client

    client = Client(
        name="Acme Dental",
        website="https://acme.example",
        industry="Dental clinic",
        contact_email="hello@acme.example",
    )
    db.add(client)
    db.commit()
    return client


def _actions_for(client_id, db):
    return db.query(OutcomeAction).filter(OutcomeAction.client_id == client_id).all()


def test_recommendation_adapter_is_idempotent_and_sanitizes_client_text(db):
    client = _make_client(db)
    recommendation = ActionRecommendation(
        client_id=client.id,
        action_text="Improve cited service pages",
        dimension="content_quality",
        estimated_impact=6.0,
        priority="high",
    )
    db.add(recommendation)
    db.commit()

    adapters.suggest_from_recommendation(recommendation, db)
    adapters.suggest_from_recommendation(recommendation, db)

    (action,) = _actions_for(client.id, db)
    assert action.source_ref == f"recommendation:{recommendation.id}"
    assert action.status == "recommended"
    assert "cited" not in action.title.lower()


def test_remediation_adapter_is_idempotent(db):
    client = _make_client(db)
    item = RemediationItem(
        client_id=client.id,
        item_type="hallucination",
        platform="chatgpt",
        label="Is Acme open 24/7?",
        detail="Incorrect opening-hours answer",
    )
    db.add(item)
    db.commit()

    adapters.suggest_from_remediation(item, db)
    adapters.suggest_from_remediation(item, db)

    (action,) = _actions_for(client.id, db)
    assert action.source_ref == f"remediation:{item.id}"
    assert action.action_type == "fact_correction"
    assert action.status == "recommended"


def test_authority_adapter_is_idempotent(db):
    client = _make_client(db)
    asset = AuthorityAsset(
        client_id=client.id,
        name="Google Business Profile",
        asset_type="directory",
        status="live",
    )
    db.add(asset)
    db.commit()

    adapters.suggest_from_authority(asset, db)
    adapters.suggest_from_authority(asset, db)

    (action,) = _actions_for(client.id, db)
    assert action.source_ref == f"authority:{asset.id}"
    assert action.action_type == "authority"
    assert action.status == "recommended"


def test_authority_adapter_skips_internal_only_assets(db):
    client = _make_client(db)
    asset = AuthorityAsset(
        client_id=client.id,
        asset_key="schema_sameas",
        name="sameAs links in site schema",
        asset_type="other",
        status="live",
    )
    db.add(asset)
    db.commit()

    assert adapters.suggest_from_authority(asset, db) is None
    assert _actions_for(client.id, db) == []


def test_link_deliverable_is_idempotent_and_updates_existing_action(db):
    client = _make_client(db)
    deliverable = ContentDeliverable(
        client_id=client.id,
        type="faq_pack",
        title="Frequently cited questions",
        body_md="# FAQ",
    )
    db.add(deliverable)
    db.commit()

    first = adapters.link_deliverable(deliverable, db)
    second = adapters.link_deliverable(deliverable, db)

    (action,) = _actions_for(client.id, db)
    assert first.id == second.id == action.id
    assert action.source_ref == f"deliverable:{deliverable.id}"
    assert action.content_deliverable_id == deliverable.id
    assert "cited" not in action.title.lower()
