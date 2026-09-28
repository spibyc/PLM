import datetime as dt
import uuid
from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, db_now, uuid_fk_col, uuid_pk
Q = Numeric(18,6); MONEY=Numeric(18,6)

class Supplier(Base):
    __tablename__='supplier'
    id: Mapped[uuid.UUID]=uuid_pk(); code: Mapped[str]=mapped_column(String(32),unique=True); name: Mapped[str]=mapped_column(String(200),unique=True)
    status: Mapped[str]=mapped_column(String(24),default='Draft'); risk_class: Mapped[str]=mapped_column(String(16),default='Medium')
    website: Mapped[str|None]=mapped_column(String(500)); notes: Mapped[str|None]=mapped_column(Text); created_at: Mapped[dt.datetime]=db_now(); created_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id')
    approved_at: Mapped[dt.datetime|None]=mapped_column(nullable=True); approved_by: Mapped[uuid.UUID|None]=uuid_fk_col('app_user.id',nullable=True)
    __table_args__=(CheckConstraint("status IN ('Draft','Approved','Suspended','Inactive')",name='status'),CheckConstraint("risk_class IN ('Low','Medium','High')",name='risk'))

class PurchaseOrder(Base):
    __tablename__='purchase_order'
    id: Mapped[uuid.UUID]=uuid_pk(); po_number: Mapped[str]=mapped_column(String(64),unique=True); supplier_id: Mapped[uuid.UUID]=uuid_fk_col('supplier.id',index=True)
    status: Mapped[str]=mapped_column(String(32),default='Draft'); currency: Mapped[str]=mapped_column(String(3),default='GBP'); revision: Mapped[int]=mapped_column(default=1)
    expected_date: Mapped[dt.date|None]=mapped_column(Date); notes: Mapped[str|None]=mapped_column(Text); created_at: Mapped[dt.datetime]=db_now(); created_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id')
    approved_at: Mapped[dt.datetime|None]=mapped_column(nullable=True); approved_by: Mapped[uuid.UUID|None]=uuid_fk_col('app_user.id',nullable=True)
    __table_args__=(CheckConstraint("status IN ('Draft','Approved','Ordered','Partially Received','Received','Closed','Cancelled')",name='status'),)

class PurchaseOrderLine(Base):
    __tablename__='purchase_order_line'
    id: Mapped[uuid.UUID]=uuid_pk(); po_id: Mapped[uuid.UUID]=uuid_fk_col('purchase_order.id',index=True); line_no: Mapped[int]=mapped_column(); item_id: Mapped[uuid.UUID]=uuid_fk_col('item.id')
    manufacturer_part_id: Mapped[uuid.UUID|None]=uuid_fk_col('manufacturer_part.id',nullable=True); supplier_part_number: Mapped[str|None]=mapped_column(String(100)); qty_ordered: Mapped[float]=mapped_column(Q)
    unit_cost: Mapped[float]=mapped_column(MONEY); qty_received: Mapped[float]=mapped_column(Q,default=0)
    __table_args__=(UniqueConstraint('po_id','line_no'),CheckConstraint('qty_ordered > 0',name='qty'),CheckConstraint('unit_cost >= 0',name='cost'),CheckConstraint('qty_received >= 0 AND qty_received <= qty_ordered',name='received'))

class GoodsReceipt(Base):
    __tablename__='goods_receipt'
    id: Mapped[uuid.UUID]=uuid_pk(); receipt_no: Mapped[str]=mapped_column(String(64),unique=True); po_id: Mapped[uuid.UUID]=uuid_fk_col('purchase_order.id',index=True); received_at: Mapped[dt.datetime]=db_now(); received_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id'); notes: Mapped[str|None]=mapped_column(Text)

class GoodsReceiptLine(Base):
    __tablename__='goods_receipt_line'
    id: Mapped[uuid.UUID]=uuid_pk(); receipt_id: Mapped[uuid.UUID]=uuid_fk_col('goods_receipt.id',index=True); po_line_id: Mapped[uuid.UUID]=uuid_fk_col('purchase_order_line.id'); lot_id: Mapped[uuid.UUID]=uuid_fk_col('inventory_lot.id',unique=True); qty: Mapped[float]=mapped_column(Q)

class Bom(Base):
    __tablename__='bom'
    id: Mapped[uuid.UUID]=uuid_pk(); bom_number: Mapped[str]=mapped_column(String(64),unique=True); product_item_id: Mapped[uuid.UUID]=uuid_fk_col('item.id',index=True); name: Mapped[str]=mapped_column(String(200)); created_at: Mapped[dt.datetime]=db_now(); created_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id')

class BomRevision(Base):
    __tablename__='bom_revision'
    id: Mapped[uuid.UUID]=uuid_pk(); bom_id: Mapped[uuid.UUID]=uuid_fk_col('bom.id',index=True); revision: Mapped[str]=mapped_column(String(32)); status: Mapped[str]=mapped_column(String(24),default='Draft'); content_hash: Mapped[str|None]=mapped_column(String(64)); change_reason: Mapped[str]=mapped_column(Text); created_at: Mapped[dt.datetime]=db_now(); created_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id'); released_at: Mapped[dt.datetime|None]=mapped_column(nullable=True); released_by: Mapped[uuid.UUID|None]=uuid_fk_col('app_user.id',nullable=True)
    __table_args__=(UniqueConstraint('bom_id','revision'),CheckConstraint("status IN ('Draft','Under Review','Released','Obsolete')",name='status'))

class BomLine(Base):
    __tablename__='bom_line'
    id: Mapped[uuid.UUID]=uuid_pk(); bom_revision_id: Mapped[uuid.UUID]=uuid_fk_col('bom_revision.id',index=True); line_no: Mapped[int]=mapped_column(); item_id: Mapped[uuid.UUID]=uuid_fk_col('item.id',index=True); quantity: Mapped[float]=mapped_column(Q); references: Mapped[str|None]=mapped_column(Text); dnp: Mapped[bool]=mapped_column(Boolean,default=False); notes: Mapped[str|None]=mapped_column(Text)
    __table_args__=(UniqueConstraint('bom_revision_id','line_no'),CheckConstraint('quantity > 0',name='qty'))

class ProductionBuild(Base):
    __tablename__='production_build'
    id: Mapped[uuid.UUID]=uuid_pk(); build_number: Mapped[str]=mapped_column(String(64),unique=True); bom_revision_id: Mapped[uuid.UUID]=uuid_fk_col('bom_revision.id',index=True); quantity: Mapped[int]=mapped_column(); status: Mapped[str]=mapped_column(String(24),default='Planned'); created_at: Mapped[dt.datetime]=db_now(); created_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id'); released_at: Mapped[dt.datetime|None]=mapped_column(nullable=True); released_by: Mapped[uuid.UUID|None]=uuid_fk_col('app_user.id',nullable=True); notes: Mapped[str|None]=mapped_column(Text)
    __table_args__=(CheckConstraint('quantity > 0',name='qty'),CheckConstraint("status IN ('Planned','In Progress','Completed','Released','Quarantined','Cancelled')",name='status'))

class BuildMaterial(Base):
    __tablename__='build_material'
    id: Mapped[uuid.UUID]=uuid_pk(); build_id: Mapped[uuid.UUID]=uuid_fk_col('production_build.id',index=True); bom_line_id: Mapped[uuid.UUID]=uuid_fk_col('bom_line.id'); lot_id: Mapped[uuid.UUID]=uuid_fk_col('inventory_lot.id',index=True); location_id: Mapped[uuid.UUID]=uuid_fk_col('location.id'); quantity: Mapped[float]=mapped_column(Q); stock_txn_id: Mapped[int]=mapped_column(ForeignKey('stock_txn.id'),unique=True); issued_at: Mapped[dt.datetime]=db_now(); issued_by: Mapped[uuid.UUID]=uuid_fk_col('app_user.id')
    __table_args__=(CheckConstraint('quantity > 0',name='qty'),)

class FinishedSerial(Base):
    __tablename__='finished_serial'
    id: Mapped[uuid.UUID]=uuid_pk(); serial_number: Mapped[str]=mapped_column(String(100),unique=True); build_id: Mapped[uuid.UUID]=uuid_fk_col('production_build.id',index=True); status: Mapped[str]=mapped_column(String(24),default='Manufactured'); manufactured_at: Mapped[dt.datetime]=db_now(); released_at: Mapped[dt.datetime|None]=mapped_column(nullable=True); released_by: Mapped[uuid.UUID|None]=uuid_fk_col('app_user.id',nullable=True)
    __table_args__=(CheckConstraint("status IN ('Manufactured','Testing','Released','Quarantined','Reworked','Scrapped','Returned')",name='status'),)
