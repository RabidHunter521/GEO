import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class AuthorityAsset(Base):
    """One authority-building checklist item for one client.

    Created ONLY when the admin picks it from AUTHORITY_ASSET_CATALOG (or adds
    a fully custom one) — never auto-seeded (spec §4: Faris's clients span
    industries; a one-size list would be noise). asset_key is the stable
    catalog key ("gbp", "crunchbase") or NULL for custom assets. Archiving is
    soft (`hidden=True`) so history survives for the Phase 5 work log. See
    docs/superpowers/specs/2026-07-11-authority-presence-tracker-design.md.
    """

    __tablename__ = "authority_assets"
    __table_args__ = (
        # One catalog key per client; custom assets (NULL key) are unconstrained.
        Index(
            "uq_authority_assets_client_key", "client_id", "asset_key", unique=True,
            postgresql_where=text("asset_key IS NOT NULL"),
            sqlite_where=text("asset_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # directory | review_platform | social | knowledge_graph | media | other
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # missing | in_progress | live | verified
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="missing", server_default="missing")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # admin-only
    # Domain to match against scan_query_source rows for provenance counts.
    provenance_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # review_platform only: [{"date","rating","count"}], oldest → newest.
    review_snapshots: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # {"name","phone","address_text"} extracted at verify time; NULL until verified.
    found_nap: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    nap_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
