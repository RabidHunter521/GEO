import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base

USER_ROLES = ("owner", "staff")


class User(Base):
    """An admin who can sign in to the admin panel.

    An account is created by an invite and becomes usable only once the
    invitee has set a password AND confirmed an authenticator app (2FA is
    mandatory). A password reset reuses the invite mechanism: it clears the
    password and 2FA and issues a new one-time link.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Stored lower-cased; unique across the whole system (one login per person).
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="staff")
    # argon2 hash. NULL until the invite is accepted (or after a reset).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Base32 TOTP secret. Generated when the invite page is first opened;
    # only trusted once totp_confirmed_at is set by a correct code.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Last accepted 30 s time step, so a code cannot be replayed.
    last_totp_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # sha256 of the one-time invite/reset token; the token itself is only ever
    # in the emailed link.
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
