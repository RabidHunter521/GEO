import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.models.base import Base


class Workspace(Base):
    """A tenant: the admins and clients that belong together.

    Today there is exactly one ("SeenBy", id = DEFAULT_WORKSPACE_ID). The
    table exists so that independent agencies can later get their own
    workspace without migrating every row again.
    """

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
