"""Client-scoped business location CRUD and its data invariants."""

import re
import unicodedata
import uuid

from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.schemas.business_location import BusinessLocationCreate, BusinessLocationPatch


class BusinessLocationValidationError(ValueError):
    """Raised when a location change would violate a service invariant."""


def get_location(
    client_id: uuid.UUID, location_id: uuid.UUID, db: Session
) -> BusinessLocation | None:
    return (
        db.query(BusinessLocation)
        .filter(BusinessLocation.client_id == client_id, BusinessLocation.id == location_id)
        .first()
    )


def list_locations(
    client_id: uuid.UUID, db: Session, active: bool = True
) -> list[BusinessLocation]:
    return (
        db.query(BusinessLocation)
        .filter(BusinessLocation.client_id == client_id, BusinessLocation.active.is_(active))
        .order_by(BusinessLocation.is_primary.desc(), BusinessLocation.name, BusinessLocation.id)
        .all()
    )


def create_location(
    client_id: uuid.UUID, payload: BusinessLocationCreate, db: Session
) -> BusinessLocation:
    values = payload.model_dump()
    is_primary = values.pop("is_primary")
    location = BusinessLocation(
        client_id=client_id,
        slug=_next_slug(client_id, payload.name, db),
        is_primary=False,
        **values,
    )
    if is_primary:
        _clear_primary(client_id, db)
        location.is_primary = True
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def patch_location(
    location: BusinessLocation, payload: BusinessLocationPatch, db: Session
) -> BusinessLocation:
    updates = payload.model_dump(exclude_unset=True)
    make_primary = updates.pop("is_primary", None)
    name = updates.get("name")
    if name is not None and name != location.name:
        updates["slug"] = _next_slug(location.client_id, name, db, exclude_location_id=location.id)
    for field, value in updates.items():
        setattr(location, field, value)
    if make_primary is True:
        _clear_primary(location.client_id, db, exclude_location_id=location.id)
        location.is_primary = True
    elif make_primary is False:
        location.is_primary = False
    db.commit()
    db.refresh(location)
    return location


def deactivate_location(location: BusinessLocation, db: Session) -> BusinessLocation:
    # Lock the full active set before counting it. A second concurrent
    # deactivation waits, then observes the first update and cannot remove the
    # remaining active location.
    active_locations = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.client_id == location.client_id, BusinessLocation.active.is_(True))
        .order_by(BusinessLocation.id)
        .with_for_update()
        .all()
    )
    locked_location = next((item for item in active_locations if item.id == location.id), None)
    if locked_location is None:
        db.refresh(location)
        return location
    if len(active_locations) <= 1:
        raise BusinessLocationValidationError("Cannot deactivate the only active location")
    locked_location.active = False
    locked_location.is_primary = False
    db.commit()
    db.refresh(locked_location)
    return locked_location


def _clear_primary(
    client_id: uuid.UUID, db: Session, exclude_location_id: uuid.UUID | None = None
) -> None:
    query = db.query(BusinessLocation).filter(
        BusinessLocation.client_id == client_id, BusinessLocation.is_primary.is_(True)
    )
    if exclude_location_id is not None:
        query = query.filter(BusinessLocation.id != exclude_location_id)
    query.update({BusinessLocation.is_primary: False}, synchronize_session=False)
    db.flush()


def _next_slug(
    client_id: uuid.UUID,
    name: str,
    db: Session,
    *,
    exclude_location_id: uuid.UUID | None = None,
) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "location"
    query = db.query(BusinessLocation.slug).filter(BusinessLocation.client_id == client_id)
    if exclude_location_id is not None:
        query = query.filter(BusinessLocation.id != exclude_location_id)
    existing_slugs = {slug for (slug,) in query.all()}
    if base not in existing_slugs:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_slugs:
        suffix += 1
    return f"{base}-{suffix}"
