"""Append-only lifecycle operations for approved business facts."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models.business_location import BusinessLocation
from app.models.truth_fact import TruthFact, TruthFactVersion
from app.schemas.truth_fact import TruthFactCreate, TruthFactVersionDraft


class TruthVaultValidationError(ValueError):
    """Raised when a requested fact lifecycle transition is not valid."""


class TruthVaultLocationNotFound(ValueError):
    """Raised when a location is absent or belongs to a different client."""


class TruthVaultFactNotFound(ValueError):
    """Raised when a fact does not exist."""


def create_fact(client_id: uuid.UUID, payload: TruthFactCreate, db: Session) -> TruthFact:
    if payload.location_id is not None:
        _validate_location(client_id, payload.location_id, db)
    fact = TruthFact(client_id=client_id, **payload.model_dump())
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def draft_version(
    fact: TruthFact, payload: TruthFactVersionDraft, db: Session
) -> TruthFactVersion:
    version = TruthFactVersion(
        truth_fact_id=fact.id,
        value_json=payload.value.model_dump(mode="json"),
        status="draft",
        source_url=payload.source_url,
        reviewer_note=payload.reviewer_note,
        effective_from=payload.effective_from,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def approve_version(
    fact_id: uuid.UUID, version_id: uuid.UUID, approved_by: str, db: Session
) -> TruthFactVersion:
    fact = _locked_fact(fact_id, db)
    draft = (
        db.query(TruthFactVersion)
        .filter(TruthFactVersion.id == version_id, TruthFactVersion.truth_fact_id == fact.id)
        .one_or_none()
    )
    if draft is None:
        raise TruthVaultValidationError("Draft version not found for this fact")
    if draft.status != "draft" or draft.effective_from is None or draft.effective_to is not None:
        raise TruthVaultValidationError("Only an open draft with an effective date can be approved")

    approved_versions = (
        db.query(TruthFactVersion)
        .filter(TruthFactVersion.truth_fact_id == fact.id, TruthFactVersion.status == "approved")
        .order_by(TruthFactVersion.effective_from, TruthFactVersion.id)
        .all()
    )
    _close_open_version_before(approved_versions, draft.effective_from)
    db.flush()

    approved_at = utcnow()
    draft.status = "approved"
    draft.approved_at = approved_at
    draft.approved_by = approved_by
    db.commit()
    db.refresh(draft)
    return draft


def retire_fact(fact_id: uuid.UUID, effective_at: datetime, db: Session) -> TruthFactVersion:
    fact = _locked_fact(fact_id, db)
    approved_versions = (
        db.query(TruthFactVersion)
        .filter(
            TruthFactVersion.truth_fact_id == fact.id,
            TruthFactVersion.status == "approved",
            TruthFactVersion.effective_to.is_(None),
        )
        .order_by(TruthFactVersion.effective_from.desc(), TruthFactVersion.id.desc())
        .all()
    )
    if not approved_versions:
        raise TruthVaultValidationError("Fact has no open approved version to retire")
    version = approved_versions[0]
    if version.effective_from is None or effective_at <= version.effective_from:
        raise TruthVaultValidationError("Retirement must follow the approved effective date")
    version.effective_to = effective_at - timedelta(microseconds=1)
    db.commit()
    db.refresh(version)
    return version


def current_facts(
    client_id: uuid.UUID, db: Session, location_id: uuid.UUID | None = None
) -> list[TruthFactVersion]:
    return facts_effective_at(client_id, utcnow(), db, location_id=location_id)


def facts_effective_at(
    client_id: uuid.UUID,
    effective_at: datetime,
    db: Session,
    location_id: uuid.UUID | None = None,
) -> list[TruthFactVersion]:
    query = (
        db.query(TruthFactVersion)
        .join(TruthFact, TruthFact.id == TruthFactVersion.truth_fact_id)
        .filter(
            TruthFact.client_id == client_id,
            TruthFactVersion.status == "approved",
            TruthFactVersion.effective_from <= effective_at,
            (TruthFactVersion.effective_to.is_(None))
            | (TruthFactVersion.effective_to >= effective_at),
        )
    )
    if location_id is None:
        query = query.filter(TruthFact.location_id.is_(None))
    else:
        query = query.filter(TruthFact.location_id == location_id)
    return query.order_by(TruthFact.fact_type, TruthFact.fact_key, TruthFactVersion.effective_from).all()


def _validate_location(client_id: uuid.UUID, location_id: uuid.UUID, db: Session) -> None:
    location = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.id == location_id, BusinessLocation.client_id == client_id)
        .first()
    )
    if location is None:
        raise TruthVaultLocationNotFound("Location not found for this client")


def _locked_fact(fact_id: uuid.UUID, db: Session) -> TruthFact:
    fact = db.query(TruthFact).filter(TruthFact.id == fact_id).with_for_update().one_or_none()
    if fact is None:
        raise TruthVaultFactNotFound("Truth fact not found")
    return fact


def _close_open_version_before(
    approved_versions: list[TruthFactVersion], new_effective_from: datetime
) -> None:
    open_versions = [version for version in approved_versions if version.effective_to is None]
    if len(open_versions) > 1:
        raise TruthVaultValidationError("Fact has more than one open approved version")
    for version in approved_versions:
        if version.effective_from is None:
            raise TruthVaultValidationError("Approved version is missing an effective date")
        if version.effective_to is not None and version.effective_to >= new_effective_from:
            raise TruthVaultValidationError("Approved version intervals overlap the new effective date")
    if open_versions:
        open_version = open_versions[0]
        if new_effective_from <= open_version.effective_from:
            raise TruthVaultValidationError("New version must follow the open approved version")
        open_version.effective_to = new_effective_from - timedelta(microseconds=1)
