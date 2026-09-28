import datetime as dt
import uuid

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def db_now(nullable: bool = False) -> Mapped[dt.datetime]:
    """Timestamp assigned by the database clock, never by the client."""
    return mapped_column(DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=nullable)


def uuid_fk_col(target: str, nullable: bool = False, **kw):  # type: ignore[no-untyped-def]
    from sqlalchemy import ForeignKey

    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=nullable, **kw)
