import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_fk_col, uuid_pk

ITEM_CLASSES = ("component", "bare_pcb", "pcba", "mechanical", "cable", "firmware", "assembly", "product")
UOMS = ("pcs", "m", "g", "ml", "kg", "l")
REV_STATUSES = (
    "Draft", "Under Review", "Approved", "Released", "NRND",
    "Obsolete", "Prohibited", "Superseded", "Discarded",
)
OPEN_STATUSES = ("Draft", "Under Review", "Approved")
AML_STATUSES = ("Proposed", "Approved", "Disqualified")
MFR_LIFECYCLE = ("Unknown", "Active", "NRND", "Last Time Buy", "EOL", "Obsolete")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class Item(Base):
    """Master identity of an internal part/item. Controlled content lives on ItemRevision."""

    __tablename__ = "item"
    id: Mapped[uuid.UUID] = uuid_pk()
    part_number: Mapped[str] = mapped_column(String(64), unique=True)
    item_class: Mapped[str] = mapped_column(String(32))
    uom: Mapped[str] = mapped_column(String(8), default="pcs")
    min_stock: Mapped[float] = mapped_column(Numeric(18, 6), default=0)
    current_released_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item_revision.id", use_alter=True, name="fk_item_current_rev")
    )
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    __table_args__ = (
        CheckConstraint(_in("item_class", ITEM_CLASSES), name="item_class"),
        CheckConstraint(_in("uom", UOMS), name="uom"),
        CheckConstraint("min_stock >= 0", name="min_stock"),
    )


class ItemRevision(Base):
    __tablename__ = "item_revision"
    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = uuid_fk_col("item.id", index=True)
    revision_label: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32), default="Draft")
    review_cycle: Mapped[int] = mapped_column(Integer, default=0)
    row_version: Mapped[int] = mapped_column(Integer, default=1)
    # --- controlled content (immutable once status != Draft; enforced by trigger) ---
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(100))
    subcategory: Mapped[str | None] = mapped_column(String(100))
    component_type: Mapped[str | None] = mapped_column(String(100))
    value: Mapped[str | None] = mapped_column(String(100))
    package: Mapped[str | None] = mapped_column(String(100))
    rohs_status: Mapped[str | None] = mapped_column(String(32))
    reach_status: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    # --- control metadata ---
    content_hash: Mapped[str | None] = mapped_column(String(64))
    supersedes_id: Mapped[uuid.UUID | None] = uuid_fk_col("item_revision.id", nullable=True)
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    modified_at: Mapped[dt.datetime] = db_now()
    modified_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("item_id", "revision_label"),
        CheckConstraint(_in("status", REV_STATUSES), name="status"),
        Index(
            "uq_item_revision_one_open",
            "item_id",
            unique=True,
            postgresql_where=text("status IN ('Draft','Under Review','Approved')"),
        ),
    )


class Manufacturer(Base):
    __tablename__ = "manufacturer"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(CITEXT, unique=True)
    website: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = db_now()


class ManufacturerPart(Base):
    __tablename__ = "manufacturer_part"
    id: Mapped[uuid.UUID] = uuid_pk()
    manufacturer_id: Mapped[uuid.UUID] = uuid_fk_col("manufacturer.id")
    mpn: Mapped[str] = mapped_column(CITEXT)
    lifecycle: Mapped[str] = mapped_column(String(32), default="Unknown")
    datasheet_url: Mapped[str | None] = mapped_column(String(500))
    rohs_status: Mapped[str | None] = mapped_column(String(32))
    reach_status: Mapped[str | None] = mapped_column(String(32))
    country_of_origin: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = db_now()
    __table_args__ = (
        UniqueConstraint("manufacturer_id", "mpn"),
        CheckConstraint(_in("lifecycle", MFR_LIFECYCLE), name="lifecycle"),
    )


class DistributorSource(Base):
    """Purchasing source for a manufacturer part (e.g. Mouser, Farnell, DigiKey)."""

    __tablename__ = "distributor_source"
    id: Mapped[uuid.UUID] = uuid_pk()
    manufacturer_part_id: Mapped[uuid.UUID] = uuid_fk_col("manufacturer_part.id", index=True)
    supplier_id: Mapped[uuid.UUID | None] = uuid_fk_col("supplier.id", nullable=True, index=True)
    distributor_name: Mapped[str] = mapped_column(CITEXT)
    source_part_number: Mapped[str | None] = mapped_column(CITEXT)
    source_url: Mapped[str | None] = mapped_column(String(500))
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    __table_args__ = (UniqueConstraint("manufacturer_part_id", "distributor_name", "source_part_number"),)


class AmlEntry(Base):
    """Approved Manufacturer List entry: one manufacturer part approved as an FFF source for an item."""

    __tablename__ = "aml_entry"
    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = uuid_fk_col("item.id", index=True)
    manufacturer_part_id: Mapped[uuid.UUID] = uuid_fk_col("manufacturer_part.id")
    status: Mapped[str] = mapped_column(String(32), default="Proposed")
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    qualification_status: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = uuid_fk_col("app_user.id", nullable=True)
    __table_args__ = (
        UniqueConstraint("item_id", "manufacturer_part_id"),
        CheckConstraint(_in("status", AML_STATUSES), name="status"),
    )
