import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
# Aliased: the model declares a column literally named `text` (below), which
# would shadow the module-level `sqlalchemy.text` function for every use
# after that column is defined in the class body.
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.models.base import Base


class TrackedQuery(Base):
    """A governed, persistent entry in a client's tracked query portfolio.

    Distinct from `ControlQuery` (a fixed causal benchmark) and from a single
    `ScanQueryResult.query_text` (one point-in-time observation): a
    TrackedQuery is the durable identity that repeated samples across scans
    attach to (`ScanQueryResult.tracked_query_id`), so answer stability can be
    measured across periods (Phase 5 Task 4) instead of only at one scan.

    `source`, `intent`, `buyer_stage`, and `risk_level` are plain varchars,
    deliberately not a PostgreSQL enum — same reasoning as
    `clients.industry_pack` (migration c0f6b4e3d9a1): adding a new value is a
    code change, not a migration. Task 2 defines the allowed values as
    Pydantic enums at the API boundary.
    """

    __tablename__ = "tracked_queries"
    __table_args__ = (
        CheckConstraint(
            "demand_weight >= 0", name="ck_tracked_queries_demand_weight_non_negative"
        ),
        CheckConstraint(
            "priority_score >= 0", name="ck_tracked_queries_priority_score_non_negative"
        ),
        # Composite FK (location_id, client_id) mirrors truth_facts: a location
        # can never be attached under a different client than the query itself.
        ForeignKeyConstraint(
            ["location_id", "client_id"],
            ["business_locations.id", "business_locations.client_id"],
            name="fk_tracked_queries_location_client",
            ondelete="CASCADE",
        ),
        # Two partial unique indexes so a brand-level query (location_id NULL)
        # and a location-level query never collide through a shared NULL —
        # Postgres treats NULL as distinct in a plain unique constraint, which
        # would silently allow duplicate brand-level rows. Both postgresql_where
        # and sqlite_where are set so the dedup rule is enforced in the SQLite
        # test suite too, not just in Postgres.
        Index(
            "uq_tracked_query_brand",
            "client_id",
            "normalized_text",
            unique=True,
            postgresql_where=sql_text("location_id IS NULL"),
            sqlite_where=sql_text("location_id IS NULL"),
        ),
        Index(
            "uq_tracked_query_location",
            "client_id",
            "location_id",
            "normalized_text",
            unique=True,
            postgresql_where=sql_text("location_id IS NOT NULL"),
            sqlite_where=sql_text("location_id IS NOT NULL"),
        ),
        Index(
            "ix_tracked_queries_client_active_priority",
            "client_id",
            "is_active",
            "priority_score",
        ),
        Index(
            "ix_tracked_queries_client_location_intent",
            "client_id",
            "location_id",
            "intent",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    buyer_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="standard", server_default="standard"
    )
    demand_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    priority_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sql_text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    scan_query_results: Mapped[list["ScanQueryResult"]] = relationship(  # noqa: F821 — ruff false-positive on SQLAlchemy string forward-ref
        "ScanQueryResult",
        back_populates="tracked_query",
    )
