import uuid
from datetime import datetime
from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ToolkitFiles(Base):
    __tablename__ = "toolkit_files"
    __table_args__ = (UniqueConstraint("client_id", name="uq_toolkit_files_client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    llms_txt: Mapped[str] = mapped_column(Text, nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    robots_txt: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    llms_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    schema_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    robots_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
