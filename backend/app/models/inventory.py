import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_fk_col, uuid_pk

LOT_STATUSES = ("Pending Inspection", "Available", "Quarantined")
TXN_TYPES = (
    "RECEIPT", "ISSUE", "RETURN", "RESERVE", "RESERVE_RELEASE", "TRANSFER_OUT", "TRANSFER_IN",
    "ADJUST", "SCRAP", "QUARANTINE", "QUARANTINE_RELEASE", "INSPECTION_ACCEPT", "INSPECTION_REJECT",
)
Q = Numeric(18, 6)


class InventoryLot(Base):
    """A received lot. Provenance columns are immutable after creation (trigger)."""

    __tablename__ = "inventory_lot"
    id: Mapped[uuid.UUID] = uuid_pk()
    lot_no: Mapped[str] = mapped_column(String(64), unique=True)
    item_id: Mapped[uuid.UUID] = uuid_fk_col("item.id", index=True)
    item_revision_id: Mapped[uuid.UUID] = uuid_fk_col("item_revision.id")
    manufacturer_part_id: Mapped[uuid.UUID | None] = uuid_fk_col("manufacturer_part.id", nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    supplier_part_number: Mapped[str | None] = mapped_column(String(100))
    purchase_order_ref: Mapped[str | None] = mapped_column(String(64))
    supplier_lot: Mapped[str | None] = mapped_column(String(100))
    manufacturer_lot: Mapped[str | None] = mapped_column(String(100))
    date_code: Mapped[str | None] = mapped_column(String(32))
    qty_received: Mapped[float] = mapped_column(Q)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date)
    received_at: Mapped[dt.datetime] = db_now()
    received_by: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    status: Mapped[str] = mapped_column(String(32), default="Pending Inspection")
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("qty_received > 0", name="qty_received"),
        CheckConstraint("status IN ('Pending Inspection','Available','Quarantined')", name="status"),
    )


class LotBalance(Base):
    """Projection of the ledger: quantity of a lot at a location. Rebuildable from stock_txn."""

    __tablename__ = "lot_balance"
    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inventory_lot.id"), primary_key=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("location.id"), primary_key=True)
    qty_on_hand: Mapped[float] = mapped_column(Q, default=0)
    qty_reserved: Mapped[float] = mapped_column(Q, default=0)
    __table_args__ = (
        CheckConstraint("qty_on_hand >= 0", name="on_hand_nonneg"),
        CheckConstraint("qty_reserved >= 0", name="reserved_nonneg"),
        CheckConstraint("qty_reserved <= qty_on_hand", name="reserved_le_on_hand"),
        Index("ix_lot_balance_location", "location_id"),
    )


class StockTxn(Base):
    """Append-only inventory ledger. Corrections are new transactions, never edits."""

    __tablename__ = "stock_txn"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    txn_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    txn_type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[dt.datetime] = db_now()
    actor_id: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    lot_id: Mapped[uuid.UUID] = uuid_fk_col("inventory_lot.id", index=True)
    item_id: Mapped[uuid.UUID] = uuid_fk_col("item.id", index=True)
    location_id: Mapped[uuid.UUID | None] = uuid_fk_col("location.id", nullable=True)
    d_on_hand: Mapped[float] = mapped_column(Q)
    d_reserved: Mapped[float] = mapped_column(Q)
    on_hand_before: Mapped[float] = mapped_column(Q)
    on_hand_after: Mapped[float] = mapped_column(Q)
    reserved_before: Mapped[float] = mapped_column(Q)
    reserved_after: Mapped[float] = mapped_column(Q)
    reason: Mapped[str | None] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(100))
    corrects_txn_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("stock_txn.id"))
    signature_id: Mapped[uuid.UUID | None] = uuid_fk_col("signature.id", nullable=True)
    __table_args__ = (
        CheckConstraint(
            "txn_type IN ('RECEIPT','ISSUE','RETURN','RESERVE','RESERVE_RELEASE','TRANSFER_OUT','TRANSFER_IN',"
            "'ADJUST','SCRAP','QUARANTINE','QUARANTINE_RELEASE','INSPECTION_ACCEPT','INSPECTION_REJECT')",
            name="txn_type",
        ),
        CheckConstraint("on_hand_after = on_hand_before + d_on_hand", name="on_hand_arith"),
        CheckConstraint("reserved_after = reserved_before + d_reserved", name="reserved_arith"),
        CheckConstraint("on_hand_after >= 0 AND reserved_after >= 0", name="nonneg"),
        Index("ix_stock_txn_occurred", "occurred_at"),
    )
