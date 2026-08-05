import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import MIN_COHORT_MEMBER_FLOOR
from app.core.time import utcnow
from app.models.base import Base


class BenchmarkCohort(Base):
    """A versioned definition of "who is comparable to whom".

    A cohort is a *definition*, not a group of rows: it records the dimensions
    (pack, country, market area, scale, coverage, period type) that make a set
    of organizations like-for-like. Membership lives in the separate private
    table below, and the aggregates live in `benchmark_snapshots`.

    `definition_version` exists because comparability rules will change. A rule
    change mints a new version rather than editing the old one, so a published
    number can always be traced to the exact definition that produced it —
    the same reasoning as `calculation_version` on snapshots.

    Dimension values are plain varchars, deliberately not PostgreSQL enums,
    matching `clients.industry_pack` and `tracked_queries.intent`: adding a
    market or a scale band is a code change, not a migration.
    """

    __tablename__ = "benchmark_cohorts"
    __table_args__ = (
        UniqueConstraint(
            "cohort_key", "definition_version", name="uq_benchmark_cohorts_key_version"
        ),
        CheckConstraint(
            f"min_member_count >= {MIN_COHORT_MEMBER_FLOOR}",
            name="ck_benchmark_cohorts_min_member_count_floor",
        ),
        Index(
            "ix_benchmark_cohorts_pack_country_scale_active",
            "industry_pack",
            "country_code",
            "scale_band",
            "is_active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Deterministic, human-readable identity built from the dimensions below,
    # e.g. "healthcare|MY|single_location|standard|month". Stored rather than
    # derived so a snapshot's lineage survives a change in key construction.
    cohort_key: Mapped[str] = mapped_column(String(255), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(16), nullable=False)
    industry_pack: Mapped[str] = mapped_column(String(32), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ISO-3166 alpha-2, normalized from the free-text `clients.country`. An
    # unmappable country is an exclusion reason, never a guess.
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    market_area: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scale_band: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_band: Mapped[str] = mapped_column(String(32), nullable=False)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)
    min_member_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=MIN_COHORT_MEMBER_FLOOR,
        server_default=str(MIN_COHORT_MEMBER_FLOOR),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list["BenchmarkCohortMembership"]] = relationship(
        "BenchmarkCohortMembership",
        back_populates="cohort",
        cascade="all, delete-orphan",
    )


class BenchmarkCohortMembership(Base):
    """Private, per-period record of whether one client counted toward a cohort.

    **Never exposed through a client or public schema.** This is the one table
    in Phase 6 that maps an aggregate back to identifiable organizations; it
    exists for operator explainability and audit, not for display.

    Every row is explainable in both directions: an excluded client must carry
    a machine-readable `exclusion_reason`, and an included client must not
    carry one. An unexplainable exclusion is indistinguishable from a bug, and
    a "reason" attached to an included client means two code paths disagree
    about what happened.
    """

    __tablename__ = "benchmark_cohort_memberships"
    __table_args__ = (
        UniqueConstraint(
            "cohort_id",
            "client_id",
            "evaluation_period_start",
            "evaluation_period_end",
            name="uq_benchmark_cohort_memberships_cohort_client_period",
        ),
        CheckConstraint(
            "is_included OR exclusion_reason IS NOT NULL",
            name="ck_benchmark_cohort_memberships_exclusion_has_reason",
        ),
        CheckConstraint(
            "NOT is_included OR exclusion_reason IS NULL",
            name="ck_benchmark_cohort_memberships_inclusion_has_no_reason",
        ),
        CheckConstraint(
            "measurement_coverage >= 0",
            name="ck_benchmark_cohort_memberships_coverage_non_negative",
        ),
        CheckConstraint(
            "evaluation_period_start <= evaluation_period_end",
            name="ck_benchmark_cohort_memberships_period_ordered",
        ),
        Index(
            "ix_benchmark_cohort_memberships_client_period",
            "client_id",
            sql_text("evaluation_period_end DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_cohorts.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    evaluation_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    evaluation_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    is_included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Machine-readable code (e.g. "opted_out", "insufficient_coverage",
    # "unmappable_country"), not prose — Task 2 owns the vocabulary.
    exclusion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Count of tracked queries with usable samples in the period; the input to
    # the coverage band, kept here so an exclusion can be re-explained later.
    measurement_coverage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    cohort: Mapped["BenchmarkCohort"] = relationship(
        "BenchmarkCohort", back_populates="memberships"
    )
