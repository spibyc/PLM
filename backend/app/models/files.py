import datetime as dt
import uuid

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_fk_col, uuid_pk


class FileObject(Base):
    """Content-addressed stored file. The storage key is derived from the SHA-256, so content cannot be overwritten."""

    __tablename__ = "file_object"
    id: Mapped[uuid.UUID] = uuid_pk()
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(200))
    storage_backend: Mapped[str] = mapped_column(String(16), default="local")
    storage_key: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    last_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_verify_result: Mapped[str | None] = mapped_column(String(32))


class Attachment(Base):
    """Links a stored file to a record. Insert-only."""

    __tablename__ = "attachment"
    id: Mapped[uuid.UUID] = uuid_pk()
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    file_object_id: Mapped[uuid.UUID] = uuid_fk_col("file_object.id")
    filename: Mapped[str] = mapped_column(String(255))
    doc_kind: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(500))
    uploaded_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    uploaded_at: Mapped[dt.datetime] = db_now()
    __table_args__ = (Index("ix_attachment_object", "object_type", "object_id"),)
