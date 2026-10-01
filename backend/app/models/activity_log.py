import uuid
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.core import request_identity
from app.core.time import utcnow


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    # The admin whose request caused this event; NULL = the system (Celery,
    # scripts, or a legacy API-key call). Stamped automatically from the
    # request's current user (app.core.request_identity).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The actor's name at the time, kept so history still reads "by Siti"
    # after Siti's account is deleted (actor_user_id then becomes NULL).
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


@event.listens_for(ActivityLog, "before_insert")
def _stamp_actor(_mapper, _connection, entry: ActivityLog) -> None:
    """Record which admin caused this event, without every call site passing
    it. Outside an admin request (Celery, scripts, the legacy system key)
    there is no current user and the actor stays NULL = "System"."""
    if entry.actor_user_id is None:
        entry.actor_user_id = request_identity.current_user_id()
        entry.actor_name = request_identity.current_name()
