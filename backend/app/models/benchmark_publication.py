import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    event,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base

BENCHMARK_PUBLICATION_STATUSES = ("draft", "approved", "published", "withdrawn")

# Fields that describe WHAT was reviewed. Once a human has approved a
# publication, none of them may change — otherwise "approved" would attest to
# something other than what is served.
FROZEN_AFTER_APPROVAL = (
    "payload",
    "payload_hash",
    "slug",
    "edition",
    "methodology_version",
    "period_start",
    "period_end",
)


class ApprovedPublicationImmutableError(Exception):
    """Raised when application code tries to alter a reviewed publication.

    Status transitions (approve → publish → withdraw) stay legal; the reviewed
    *content* does not. Correcting a published edition means withdrawing it and
    issuing a new one, so the record of what was public and when survives.
    """


class BenchmarkPublication(Base):
    """A reviewed, immutable aggregate dataset — one edition of the index.

    The lifecycle is deliberately four states rather than a boolean: draft is
    machine-generated and unreviewed, approved is a human attesting to a
    specific payload, published is that payload being served anonymously, and
    withdrawn closes public access **without deleting the record**. A withdrawn
    edition still has to be answerable for — it was public, and deleting the
    row would erase the evidence of what was said.

    `payload_hash` is what makes approval mean anything. It is the hash of the
    exact bytes reviewed, so publishing can promote reviewed content instead of
    recomputing and hoping the numbers still match.
    """

    __tablename__ = "benchmark_publications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'published', 'withdrawn')",
            name="ck_benchmark_publications_status_vocabulary",
        ),
        # Separation of duty. With a single shared admin API key this cannot be
        # an authentication boundary, so it is enforced here as a procedural
        # one: the service refuses an approval naming the same actor that
        # generated the draft, and the database refuses to store one.
        CheckConstraint(
            "approved_by IS NULL OR approved_by <> generated_by",
            name="ck_benchmark_publications_approver_differs_from_generator",
        ),
        CheckConstraint(
            "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_benchmark_publications_approved_records_actor",
        ),
        CheckConstraint(
            "status <> 'published' OR (published_at IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_benchmark_publications_published_was_approved",
        ),
        CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_benchmark_publications_withdrawn_records_time",
        ),
        CheckConstraint(
            "period_start <= period_end",
            name="ck_benchmark_publications_period_ordered",
        ),
        Index("ix_benchmark_publications_status_period", "status", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    edition: Mapped[str] = mapped_column(String(64), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    # The reviewed aggregate dataset. Contains cohort-level ranges only — no
    # cohort keys, no member counts, no client identifiers, no market-area cuts.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


@event.listens_for(BenchmarkPublication, "before_update")
def _reject_content_change_after_approval(mapper, connection, target) -> None:
    """Freeze reviewed content once approved, while leaving status free.

    Reads the persisted row rather than SQLAlchemy attribute history for the
    same reason the snapshot guard does: `commit()` expires instances, so an
    untouched attribute has no history to inspect and the guard would pass
    silently on exactly the updates it exists to catch.
    """
    table = BenchmarkPublication.__table__
    persisted = connection.execute(
        select(
            table.c.approved_at,
            *[table.c[name] for name in FROZEN_AFTER_APPROVAL],
        ).where(table.c.id == target.id)
    ).one_or_none()
    if persisted is None or persisted.approved_at is None:
        return

    for name in FROZEN_AFTER_APPROVAL:
        if getattr(target, name) != getattr(persisted, name):
            raise ApprovedPublicationImmutableError(
                f"publication {target.id} is approved; {name} cannot change. "
                "Withdraw it and issue a new edition instead."
            )
