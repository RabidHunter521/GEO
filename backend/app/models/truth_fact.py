import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DDL,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


TRUTH_FACT_VERSION_STATUSES = ("draft", "approved", "retired")


class TruthFact(Base):
    """The stable identity for a brand-wide or location-specific business fact."""

    __tablename__ = "truth_facts"
    __table_args__ = (
        Index(
            "uq_truth_fact_brand",
            "client_id",
            "fact_type",
            "fact_key",
            unique=True,
            postgresql_where=text("location_id IS NULL"),
            sqlite_where=text("location_id IS NULL"),
        ),
        Index(
            "uq_truth_fact_location",
            "client_id",
            "location_id",
            "fact_type",
            "fact_key",
            unique=True,
            postgresql_where=text("location_id IS NOT NULL"),
            sqlite_where=text("location_id IS NOT NULL"),
        ),
        Index("ix_truth_facts_client_fact_type", "client_id", "fact_type"),
        Index("ix_truth_facts_location", "location_id"),
        ForeignKeyConstraint(
            ["location_id", "client_id"],
            ["business_locations.id", "business_locations.client_id"],
            name="fk_truth_facts_location_client",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class TruthFactVersion(Base):
    """An auditable value and validity period for a truth fact."""

    __tablename__ = "truth_fact_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'retired')",
            name="ck_truth_fact_versions_status",
        ),
        Index(
            "uq_truth_fact_versions_open_approved",
            "truth_fact_id",
            unique=True,
            postgresql_where=text("status = 'approved' AND effective_to IS NULL"),
            sqlite_where=text("status = 'approved' AND effective_to IS NULL"),
        ),
        Index("ix_truth_fact_versions_fact_status", "truth_fact_id", "status"),
        Index("ix_truth_fact_versions_effective", "truth_fact_id", "effective_from", "effective_to"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    truth_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("truth_facts.id"), nullable=False
    )
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


event.listen(
    TruthFactVersion.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER trg_truth_fact_versions_append_only_update
        BEFORE UPDATE ON truth_fact_versions
        FOR EACH ROW
        WHEN NOT (
            (
                OLD.status = 'draft'
                AND NEW.status = 'approved'
                AND OLD.approved_at IS NULL
                AND OLD.approved_by IS NULL
                AND NEW.approved_at IS NOT NULL
                AND NEW.approved_by IS NOT NULL
                AND NEW.effective_from IS NOT NULL
                AND OLD.effective_to IS NULL
                AND NEW.effective_to IS NULL
                AND NEW.id IS OLD.id
                AND NEW.truth_fact_id IS OLD.truth_fact_id
                AND NEW.value_json IS OLD.value_json
                AND NEW.source_url IS OLD.source_url
                AND NEW.reviewer_note IS OLD.reviewer_note
                AND NEW.effective_from IS OLD.effective_from
                AND NEW.created_at IS OLD.created_at
            )
            OR
            (
                OLD.status = 'approved'
                AND NEW.status = 'approved'
                AND OLD.effective_from IS NOT NULL
                AND OLD.effective_to IS NULL
                AND NEW.effective_to IS NOT NULL
                AND NEW.effective_to >= OLD.effective_from
                AND NEW.id IS OLD.id
                AND NEW.truth_fact_id IS OLD.truth_fact_id
                AND NEW.value_json IS OLD.value_json
                AND NEW.source_url IS OLD.source_url
                AND NEW.reviewer_note IS OLD.reviewer_note
                AND NEW.effective_from IS OLD.effective_from
                AND NEW.approved_at IS OLD.approved_at
                AND NEW.approved_by IS OLD.approved_by
                AND NEW.created_at IS OLD.created_at
            )
        )
        BEGIN
            SELECT RAISE(ABORT, 'truth fact versions are append-only');
        END;
        """
    ).execute_if(dialect="sqlite"),
)

event.listen(
    TruthFactVersion.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER trg_truth_fact_versions_append_only_delete
        BEFORE DELETE ON truth_fact_versions
        FOR EACH ROW BEGIN
            SELECT RAISE(ABORT, 'truth fact versions are append-only');
        END;
        """
    ).execute_if(dialect="sqlite"),
)
