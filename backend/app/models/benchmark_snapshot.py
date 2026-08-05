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
    Numeric,
    String,
    UniqueConstraint,
    event,
    select,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base


class ApprovedSnapshotImmutableError(Exception):
    """Raised when application code tries to change or delete an approved snapshot.

    Corrections are made by writing a new `calculation_version`, never by
    editing a number someone has already been shown.
    """


class BenchmarkSnapshot(Base):
    """An immutable aggregate result for one cohort, period, and metric.

    The privacy rules of the whole data moat land in this table's constraints
    rather than only in the service that fills it:

    - `suppressed` and the aggregate columns are strictly biconditional. A
      suppressed row carries no p25/p50/p75/mean, and an unsuppressed row
      carries all four. A suppressed-but-populated row is the single most
      dangerous row Phase 6 could write, because every reader downstream
      trusts the flag and would happily render the values beside it.
    - `contributing_member_count` can never exceed `eligible_member_count`;
      the pair is what the suppression rules are checked against, and an
      inverted pair would let a 3-contributor metric look like a 12-member one.

    Immutability is enforced twice on purpose: a plpgsql trigger in migration
    `e2b8d6a5f1c3` covers everything that can reach the table, and the ORM
    guard at the bottom of this module covers application writes so the
    behaviour is testable on SQLite and fails with a domain error rather than
    a raw database exception.
    """

    __tablename__ = "benchmark_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "cohort_id",
            "period_start",
            "period_end",
            "metric_key",
            "calculation_version",
            name="uq_benchmark_snapshots_cohort_period_metric_version",
        ),
        CheckConstraint(
            "NOT suppressed OR "
            "(p25 IS NULL AND p50 IS NULL AND p75 IS NULL AND mean IS NULL)",
            name="ck_benchmark_snapshots_suppressed_has_no_values",
        ),
        CheckConstraint(
            "suppressed OR "
            "(p25 IS NOT NULL AND p50 IS NOT NULL AND p75 IS NOT NULL AND mean IS NOT NULL)",
            name="ck_benchmark_snapshots_unsuppressed_has_values",
        ),
        CheckConstraint(
            "p25 IS NULL OR (p25 <= p50 AND p50 <= p75)",
            name="ck_benchmark_snapshots_percentiles_ordered",
        ),
        CheckConstraint(
            "contributing_member_count <= eligible_member_count",
            name="ck_benchmark_snapshots_contributing_within_eligible",
        ),
        CheckConstraint(
            "eligible_member_count >= 0 AND contributing_member_count >= 0",
            name="ck_benchmark_snapshots_counts_non_negative",
        ),
        CheckConstraint(
            "period_start <= period_end",
            name="ck_benchmark_snapshots_period_ordered",
        ),
        Index(
            "ix_benchmark_snapshots_cohort_period_metric",
            "cohort_id",
            sql_text("period_end DESC"),
            "metric_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # RESTRICT, not CASCADE: an approved aggregate outlives cohort housekeeping.
    # Deleting a cohort that has snapshots must be a deliberate, visible act.
    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_cohorts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)
    eligible_member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contributing_member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Numeric, not Float: these are published figures, and binary float drift
    # would make a re-run of the same calculation version look like a change.
    p25: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    p50: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    p75: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    mean: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    suppressed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    suppression_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cohort: Mapped["BenchmarkCohort"] = relationship("BenchmarkCohort")  # noqa: F821


def _persisted_approved_at(connection, target) -> datetime | None:
    """Read `approved_at` as it exists in the database right now.

    Deliberately a fresh SELECT rather than SQLAlchemy attribute history: after
    a `commit()` the session expires its instances, so an untouched
    `approved_at` has no loaded history to inspect and the guard would silently
    pass. Reading the row mirrors exactly what the plpgsql trigger sees in
    `OLD.approved_at`, so the two enforcement points cannot drift.
    """
    table = BenchmarkSnapshot.__table__
    return connection.execute(
        select(table.c.approved_at).where(table.c.id == target.id)
    ).scalar_one_or_none()


@event.listens_for(BenchmarkSnapshot, "before_update")
def _reject_update_of_approved_snapshot(mapper, connection, target) -> None:
    if _persisted_approved_at(connection, target) is not None:
        raise ApprovedSnapshotImmutableError(
            f"benchmark snapshot {target.id} is approved and cannot be modified; "
            "write a new calculation_version instead"
        )


@event.listens_for(BenchmarkSnapshot, "before_delete")
def _reject_delete_of_approved_snapshot(mapper, connection, target) -> None:
    if _persisted_approved_at(connection, target) is not None:
        raise ApprovedSnapshotImmutableError(
            f"benchmark snapshot {target.id} is approved and cannot be deleted; "
            "withdraw its publication instead"
        )
