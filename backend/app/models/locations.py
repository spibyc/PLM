import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_fk_col, uuid_pk

LOCATION_KINDS = ("site", "room", "cabinet", "drawer", "bin", "compartment")


class Location(Base):
    __tablename__ = "location"
    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[uuid.UUID | None] = uuid_fk_col("location.id", nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(1000))  # e.g. "S1/R2/C03" for display & prefix queries
    is_quarantine: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    __table_args__ = (
        CheckConstraint("kind IN ('site','room','cabinet','drawer','bin','compartment')", name="kind"),
        CheckConstraint("code ~ '^[A-Z0-9][A-Z0-9-]*$'", name="code_format"),
    )
