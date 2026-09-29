import datetime as dt
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require
from app.context import Actor
from app.core.errors import NotFound
from app.db import get_db
from app.models import InventoryLot
from app.services import files, inventory, locations

router = APIRouter(prefix="/api", tags=["inventory"])


class LocationIn(BaseModel):
    parent_id: uuid.UUID | None = None
    kind: str
    segment: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=200)
    is_quarantine: bool = False
    notes: str | None = None


class LocationEdit(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    notes: str | None = None
    reason: str = Field(min_length=3)


class LocationRetire(BaseModel):
    reason: str = Field(min_length=3)


class ReceiveIn(BaseModel):
    item_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    location_id: uuid.UUID
    manufacturer_part_id: uuid.UUID | None = None
    supplier_name: str | None = Field(default=None, max_length=200)
    supplier_part_number: str | None = Field(default=None, max_length=100)
    purchase_order_ref: str | None = Field(default=None, max_length=64)
    supplier_lot: str | None = Field(default=None, max_length=100)
    manufacturer_lot: str | None = Field(default=None, max_length=100)
    date_code: str | None = Field(default=None, max_length=32)
    expiry_date: dt.date | None = None
    notes: str | None = None


class QtyIn(BaseModel):
    location_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    reference: str = ""
    comment: str | None = None


class TransferIn(BaseModel):
    qty_reserved: Decimal = Decimal(0)
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    comment: str | None = None


class AdjustIn(BaseModel):
    location_id: uuid.UUID
    delta: Decimal
    reason: str = Field(min_length=3)
    comment: str | None = None
    corrects_txn_id: int | None = None


class ScrapIn(BaseModel):
    location_id: uuid.UUID
    qty: Decimal = Field(gt=0)
    reason: str = Field(min_length=3)
    comment: str | None = None


class QuarantineIn(BaseModel):
    reason: str = Field(min_length=3)
    comment: str | None = None


class SignedIn(BaseModel):
    password: str
    comment: str | None = None


class InspectIn(SignedIn):
    accept: bool


# ---------------- locations ----------------

@router.get("/locations")
def list_locations(include_system: bool = False, actor: Actor = Depends(require("location:read")), db: Session = Depends(get_db)) -> list[dict]:
    return locations.list_locations(db, include_system=include_system)


@router.post("/locations")
def create_location(body: LocationIn, actor: Actor = Depends(require("location:write")),
                    db: Session = Depends(get_db)) -> dict:
    loc = locations.create_location(db, actor, body.parent_id, body.kind, body.segment, body.name,
                                    body.is_quarantine, body.notes)
    db.commit()
    return locations.location_detail(db, loc.id)


@router.get("/locations/by-code/{code}")
def location_by_code(code: str, actor: Actor = Depends(require("location:read")), db: Session = Depends(get_db)) -> dict:
    return locations.location_detail(db, code=code.upper())


@router.get("/locations/{loc_id}")
def location(loc_id: uuid.UUID, actor: Actor = Depends(require("location:read")), db: Session = Depends(get_db)) -> dict:
    return locations.location_detail(db, loc_id)


@router.patch("/locations/{loc_id}")
def edit_location(loc_id: uuid.UUID, body: LocationEdit, actor: Actor = Depends(require("location:write")),
                  db: Session = Depends(get_db)) -> dict:
    locations.update_location(db, actor, loc_id, body.name, body.is_active, body.notes, body.reason)
    db.commit()
    return locations.location_detail(db, loc_id)


@router.post("/locations/{loc_id}/retire")
def retire_location(loc_id: uuid.UUID, body: LocationRetire,
                    actor: Actor = Depends(require("location:delete")), db: Session = Depends(get_db)) -> dict:
    locations.retire_location(db, actor, loc_id, body.reason)
    db.commit()
    return locations.location_detail(db, loc_id)


# ---------------- lots ----------------

@router.get("/lots")
def list_lots(q: str | None = None, status: str | None = None, item_id: uuid.UUID | None = None,
              include_empty: bool = False, limit: int = Query(50, le=500), offset: int = 0,
              actor: Actor = Depends(require("inventory:read")), db: Session = Depends(get_db)) -> dict:
    return inventory.list_lots(db, q, status, item_id, include_empty, limit, offset)


@router.post("/lots")
def receive(body: ReceiveIn, actor: Actor = Depends(require("inventory:receive")), db: Session = Depends(get_db)) -> dict:
    lot = inventory.receive(db, actor, **body.model_dump())
    db.commit()
    return inventory.lot_detail(db, lot.id)


@router.get("/lots/by-number/{lot_no}")
def lot_by_number(lot_no: str, actor: Actor = Depends(require("inventory:read")), db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import select

    lot = db.execute(select(InventoryLot).where(InventoryLot.lot_no == lot_no)).scalar_one_or_none()
    if lot is None:
        raise NotFound("Lot")
    return inventory.lot_detail(db, lot.id)


@router.get("/lots/{lot_id}")
def lot(lot_id: uuid.UUID, actor: Actor = Depends(require("inventory:read")), db: Session = Depends(get_db)) -> dict:
    return inventory.lot_detail(db, lot_id)


def _done(db: Session, lot_id: uuid.UUID) -> dict:
    db.commit()
    return inventory.lot_detail(db, lot_id)


@router.post("/lots/{lot_id}/inspect")
def inspect(lot_id: uuid.UUID, body: InspectIn, actor: Actor = Depends(require("inventory:read")),
            db: Session = Depends(get_db)) -> dict:
    inventory.inspect(db, actor, lot_id, body.accept, body.password, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/issue")
def issue(lot_id: uuid.UUID, body: QtyIn, actor: Actor = Depends(require("inventory:transact")),
          db: Session = Depends(get_db)) -> dict:
    inventory.issue(db, actor, lot_id, body.location_id, body.qty, body.reference, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/return")
def ret(lot_id: uuid.UUID, body: QtyIn, actor: Actor = Depends(require("inventory:transact")),
        db: Session = Depends(get_db)) -> dict:
    inventory.return_stock(db, actor, lot_id, body.location_id, body.qty, body.reference, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/reserve")
def reserve(lot_id: uuid.UUID, body: QtyIn, actor: Actor = Depends(require("inventory:transact")),
            db: Session = Depends(get_db)) -> dict:
    inventory.reserve(db, actor, lot_id, body.location_id, body.qty, body.reference, False, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/release-reservation")
def unreserve(lot_id: uuid.UUID, body: QtyIn, actor: Actor = Depends(require("inventory:transact")),
              db: Session = Depends(get_db)) -> dict:
    inventory.reserve(db, actor, lot_id, body.location_id, body.qty, body.reference, True, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/transfer")
def transfer(lot_id: uuid.UUID, body: TransferIn, actor: Actor = Depends(require("inventory:transact")),
             db: Session = Depends(get_db)) -> dict:
    inventory.transfer(db, actor, lot_id, body.from_location_id, body.to_location_id, body.qty, body.comment,
                       qty_reserved=body.qty_reserved)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/adjust")
def adjust(lot_id: uuid.UUID, body: AdjustIn, actor: Actor = Depends(require("inventory:adjust")),
           db: Session = Depends(get_db)) -> dict:
    inventory.adjust(db, actor, lot_id, body.location_id, body.delta, body.reason, body.comment, body.corrects_txn_id)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/scrap")
def scrap(lot_id: uuid.UUID, body: ScrapIn, actor: Actor = Depends(require("inventory:adjust")),
          db: Session = Depends(get_db)) -> dict:
    inventory.scrap(db, actor, lot_id, body.location_id, body.qty, body.reason, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/quarantine")
def quarantine(lot_id: uuid.UUID, body: QuarantineIn, actor: Actor = Depends(require("inventory:quarantine")),
               db: Session = Depends(get_db)) -> dict:
    inventory.quarantine(db, actor, lot_id, body.reason, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/release-quarantine")
def release(lot_id: uuid.UUID, body: SignedIn, actor: Actor = Depends(require("inventory:read")),
            db: Session = Depends(get_db)) -> dict:
    inventory.release_quarantine(db, actor, lot_id, body.password, body.comment)
    return _done(db, lot_id)


@router.post("/lots/{lot_id}/attachments")
def lot_upload(lot_id: uuid.UUID, file: UploadFile = File(...), doc_kind: str = Form(...),
               description: str | None = Form(None), actor: Actor = Depends(require("files:upload")),
               db: Session = Depends(get_db)) -> dict:
    lot = db.get(InventoryLot, lot_id)
    if lot is None:
        raise NotFound("Lot")
    files.attach(db, actor, "inventory_lot", lot.id, file.file, file.filename or "", doc_kind, description, lot.lot_no)
    return _done(db, lot_id)


@router.get("/transactions")
def transactions(lot_id: uuid.UUID | None = None, item_id: uuid.UUID | None = None, txn_type: str | None = None,
                 limit: int = Query(100, le=1000), offset: int = 0, actor: Actor = Depends(require("inventory:read")),
                 db: Session = Depends(get_db)) -> dict:
    return inventory.ledger(db, lot_id, item_id, txn_type, limit, offset)


@router.get("/inventory/verify")
def verify(actor: Actor = Depends(require("files:verify")), db: Session = Depends(get_db)) -> dict:
    return inventory.verify_balances(db)


