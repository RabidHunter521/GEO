"""Repair-safe migration of legacy Client fields into the Truth Vault."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.business_location import BusinessLocation
from app.models.client import Client
from app.models.truth_fact import TruthFact, TruthFactVersion


CLIENT_FACT_MAP = {
    "official_name": "name",
    "website": "website",
    "industry": "industry",
    "description": "description",
    "phone": "phone",
}
LOCATION_FACT_MAP = {
    "city": "city",
    "state": "state",
    "country": "country",
}
BACKFILL_SOURCE_URL = "client-record://backfill"
BACKFILL_REVIEWER = "system:migration"


@dataclass(frozen=True)
class BackfillResult:
    locations_created: int = 0
    facts_created: int = 0
    versions_created: int = 0


def backfill_client_truth(client_id: uuid.UUID, db: Session) -> BackfillResult:
    """Create missing initial approved truth records from a client's legacy fields.

    Existing facts and their versions are never changed: this makes the function
    safe to call after the SQL migration as a repair operation.
    """
    client = db.query(Client).filter(Client.id == client_id).one_or_none()
    if client is None:
        raise ValueError("Client not found")

    location, location_created = _primary_location(client, db)
    facts_created = 0
    versions_created = 0
    effective_from = client.created_at or utcnow()

    for fact_key, client_field in CLIENT_FACT_MAP.items():
        value = _clean_value(getattr(client, client_field))
        if value is None:
            continue
        fact, created = _fact(client.id, None, "business", fact_key, db)
        facts_created += int(created)
        versions_created += int(_initial_approved_version(fact, value, effective_from, db))

    for fact_key, client_field in LOCATION_FACT_MAP.items():
        value = _clean_value(getattr(client, client_field))
        if value is None:
            continue
        fact, created = _fact(client.id, location.id, "location", fact_key, db)
        facts_created += int(created)
        versions_created += int(_initial_approved_version(fact, value, effective_from, db))

    db.commit()
    return BackfillResult(
        locations_created=int(location_created),
        facts_created=facts_created,
        versions_created=versions_created,
    )


def _primary_location(client: Client, db: Session) -> tuple[BusinessLocation, bool]:
    location = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.client_id == client.id, BusinessLocation.is_primary.is_(True))
        .one_or_none()
    )
    if location is not None:
        return location, False

    location = BusinessLocation(
        client_id=client.id,
        name=_clean_value(client.name) or "Primary location",
        slug=f"primary-{client.id}",
        is_primary=True,
        website=_clean_value(client.website),
        city=_clean_value(client.city),
        state=_clean_value(client.state),
        country=_location_country(_clean_value(client.country)),
        phone=_clean_value(client.phone),
    )
    db.add(location)
    db.flush()
    return location, True


def _fact(
    client_id: uuid.UUID,
    location_id: uuid.UUID | None,
    fact_type: str,
    fact_key: str,
    db: Session,
) -> tuple[TruthFact, bool]:
    query = db.query(TruthFact).filter(
        TruthFact.client_id == client_id,
        TruthFact.fact_type == fact_type,
        TruthFact.fact_key == fact_key,
    )
    query = query.filter(TruthFact.location_id.is_(None) if location_id is None else TruthFact.location_id == location_id)
    fact = query.one_or_none()
    if fact is not None:
        return fact, False

    fact = TruthFact(
        client_id=client_id,
        location_id=location_id,
        fact_type=fact_type,
        fact_key=fact_key,
    )
    db.add(fact)
    db.flush()
    return fact, True


def _initial_approved_version(
    fact: TruthFact, value: str, effective_from: datetime, db: Session
) -> bool:
    if db.query(TruthFactVersion).filter(TruthFactVersion.truth_fact_id == fact.id).first() is not None:
        return False

    db.add(
        TruthFactVersion(
            truth_fact_id=fact.id,
            value_json={"value": value, "display_value": value},
            status="approved",
            source_url=BACKFILL_SOURCE_URL,
            effective_from=effective_from,
            approved_at=utcnow(),
            approved_by=BACKFILL_REVIEWER,
        )
    )
    return True


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _location_country(value: str | None) -> str | None:
    """Return an ISO-2-shaped location country without losing legacy truth data."""
    if value is None or len(value) != 2 or not value.isascii() or not value.isalpha():
        return None
    return value.upper()
