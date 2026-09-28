import datetime as dt
import uuid
from sqlalchemy import Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, db_now, uuid_fk_col, uuid_pk

class ControlledDocument(Base):
    __tablename__ = "controlled_document"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240), index=True)
    document_type: Mapped[str] = mapped_column(String(64), index=True)
    owner_department: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(16), default="Internal")
    external_reference: Mapped[str | None] = mapped_column(String(240))
    product_or_project: Mapped[str | None] = mapped_column(String(160), index=True)
    retention_years: Mapped[int] = mapped_column(Integer, default=10)
    review_interval_months: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")

class DocumentRevision(Base):
    __tablename__ = "document_revision"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = uuid_fk_col("controlled_document.id")
    revision: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="Draft", index=True)
    change_summary: Mapped[str] = mapped_column(Text)
    file_object_id: Mapped[uuid.UUID | None] = uuid_fk_col("file_object.id", nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    effective_date: Mapped[dt.date | None] = mapped_column(Date)
    review_due_date: Mapped[dt.date | None] = mapped_column(Date)
    retention_until: Mapped[dt.date | None] = mapped_column(Date)
    prepared_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    created_at: Mapped[dt.datetime] = db_now()
    released_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    released_by: Mapped[uuid.UUID | None] = uuid_fk_col("app_user.id", nullable=True)
    obsolete_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)
    obsolete_by: Mapped[uuid.UUID | None] = uuid_fk_col("app_user.id", nullable=True)
    __table_args__ = (UniqueConstraint("document_id", "revision", name="uq_document_revision_label"),)
