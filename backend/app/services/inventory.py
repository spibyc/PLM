"""Lot-based inventory with an append-only ledger.

Invariants (enforced by DB constraints, not only by this code):
  * on_hand >= 0, 0 <= reserved <= on_hand for every lot/location balance
  * every ledger row satisfies after = before + delta
Concurrency: every operation first locks the lot row (serialising all movements of that lot), then the
balance rows it touches. Correlated legs (e.g. transfers) share a correlation_id.
"""
import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.errors import Conflict, DomainError, NotFound
from app.models import (
    AmlEntry, Attachment, FileObject, InventoryLot, Item, ItemRevision, Location, LotBalance, Manufacturer,
    ManufacturerPart, StockTxn, User,
)
from app.services import audit, signatures
from app.services.numbering import next_number

BLOCKED_REV = ("Prohibited", "Obsolete")


def _blocked_items() -> Select:
    return (select(Item.id).join(ItemRevision, ItemRevision.id == Item.current_released_revision_id)
            .where(ItemRevision.status.in_(BLOCKED_REV)))


def available_filter(q: Select) -> Select:
    """Restrict a query joined to LotBalance to stock that may be allocated to normal production."""
    return (q.join(Location, Location.id == LotBalance.location_id)
            .join(ItemRevision, ItemRevision.id == InventoryLot.item_revision_id)
            .where(InventoryLot.status == "Available",
                   Location.is_quarantine.is_(False),
                   or_(InventoryLot.expiry_date.is_(None), InventoryLot.expiry_date >= func.current_date()),
                   ItemRevision.status.notin_(BLOCKED_REV),
                   InventoryLot.item_id.notin_(_blocked_items())))


def usability_problems(db: Session, lot: InventoryLot, location: Location | None = None) -> list[str]:
    probs = []
    if lot.status != "Available":
        probs.append(f"Lot status is {lot.status}")
    today = db.execute(select(func.current_date())).scalar_one()
    if lot.expiry_date and lot.expiry_date < today:
        probs.append(f"Lot expired on {lot.expiry_date.isoformat()}")
    rev = db.get(ItemRevision, lot.item_revision_id)
    if rev and rev.status in BLOCKED_REV:
        probs.append(f"Received item revision {rev.revision_label} is {rev.status}")
    item = db.get(Item, lot.item_id)
    if item and item.current_released_revision_id:
        cur = db.get(ItemRevision, item.current_released_revision_id)
        if cur and cur.status in BLOCKED_REV and cur.id != lot.item_revision_id:
            probs.append(f"Item's current revision {cur.revision_label} is {cur.status}")
    if location is not None and location.is_quarantine:
        probs.append(f"Location {location.code} is a quarantine location")
    return probs


def _q(v: Any) -> Decimal:
    d = Decimal(str(v))
    return d


def _check_qty(item: Item, qty: Decimal, allow_negative: bool = False) -> None:
    if qty == 0 or (qty < 0 and not allow_negative):
        raise DomainError("Quantity must be greater than zero", "validation")
    if item.uom == "pcs" and qty != qty.to_integral_value():
        raise DomainError("Quantities in pcs must be whole numbers", "validation")


def _lock_lot(db: Session, lot_id: uuid.UUID) -> tuple[InventoryLot, Item]:
    lot = db.execute(select(InventoryLot).where(InventoryLot.id == lot_id).with_for_update()).scalar_one_or_none()
    if lot is None:
        raise NotFound("Lot")
    item = db.get(Item, lot.item_id)
    assert item is not None
    return lot, item


def _location(db: Session, loc_id: uuid.UUID, must_be_active: bool = True) -> Location:
    loc = db.get(Location, loc_id)
    if loc is None:
        raise NotFound("Location")
    if must_be_active and not loc.is_active:
        raise DomainError(f"Location {loc.code} is inactive", "validation")
    return loc


def _post(db: Session, actor: Actor, *, txn_type: str, lot: InventoryLot, location_id: uuid.UUID,
          d_on_hand: Decimal, d_reserved: Decimal, correlation_id: uuid.UUID, reason: str | None = None,
          comment: str | None = None, reference: str | None = None, corrects_txn_id: int | None = None,
          signature_id: uuid.UUID | None = None) -> StockTxn:
    db.execute(pg_insert(LotBalance).values(lot_id=lot.id, location_id=location_id, qty_on_hand=0, qty_reserved=0)
               .on_conflict_do_nothing())
    bal = db.execute(select(LotBalance).where(LotBalance.lot_id == lot.id, LotBalance.location_id == location_id)
                     .with_for_update()).scalar_one()
    oh0, rs0 = Decimal(bal.qty_on_hand), Decimal(bal.qty_reserved)
    oh1, rs1 = oh0 + d_on_hand, rs0 + d_reserved
    if oh1 < 0:
        raise Conflict(f"Insufficient stock: {oh0} on hand at this location", "insufficient_stock")
    if rs1 < 0:
        raise Conflict(f"Cannot release more than reserved ({rs0})", "insufficient_reserved")
    if rs1 > oh1:
        raise Conflict(f"Insufficient unreserved stock: {oh0 - rs0} available at this location", "insufficient_stock")
    bal.qty_on_hand, bal.qty_reserved = oh1, rs1
    t = StockTxn(correlation_id=correlation_id, txn_type=txn_type, actor_id=actor.user_id, lot_id=lot.id,
                 item_id=lot.item_id, location_id=location_id, d_on_hand=d_on_hand, d_reserved=d_reserved,
                 on_hand_before=oh0, on_hand_after=oh1, reserved_before=rs0, reserved_after=rs1, reason=reason,
                 comment=comment, reference=reference, corrects_txn_id=corrects_txn_id, signature_id=signature_id)
    db.add(t)
    db.flush()
    audit.record(db, actor, "inventory_transaction", "inventory_lot", lot.id, lot.lot_no,
                 after={"txn_id": t.id, "txn_type": txn_type, "location_id": location_id,
                        "d_on_hand": d_on_hand, "d_reserved": d_reserved, "on_hand_after": oh1,
                        "reserved_after": rs1, "reference": reference},
                 reason=" | ".join(x for x in (reason, comment) if x) or None)
    return t


def _post_status(db: Session, actor: Actor, lot: InventoryLot, txn_type: str, new_status: str, reason: str | None,
                 comment: str | None, signature_id: uuid.UUID | None = None) -> None:
    oh, rs = db.execute(select(func.coalesce(func.sum(LotBalance.qty_on_hand), 0),
                               func.coalesce(func.sum(LotBalance.qty_reserved), 0))
                        .where(LotBalance.lot_id == lot.id)).one()
    old = lot.status
    lot.status = new_status
    db.add(StockTxn(correlation_id=uuid.uuid4(), txn_type=txn_type, actor_id=actor.user_id, lot_id=lot.id,
                    item_id=lot.item_id, location_id=None, d_on_hand=0, d_reserved=0, on_hand_before=oh,
                    on_hand_after=oh, reserved_before=rs, reserved_after=rs, reason=reason, comment=comment,
                    signature_id=signature_id))
    db.flush()
    signatures.transition(db, actor, "inventory_lot", lot.id, old, new_status,
                          " | ".join(x for x in (reason, comment) if x) or None, signature_id, lot.lot_no)


# ---------------- operations ----------------

def receive(db: Session, actor: Actor, *, item_id: uuid.UUID, qty: Any, location_id: uuid.UUID,
            manufacturer_part_id: uuid.UUID | None = None, supplier_name: str | None = None,
            supplier_part_number: str | None = None, purchase_order_ref: str | None = None,
            supplier_lot: str | None = None, manufacturer_lot: str | None = None, date_code: str | None = None,
            expiry_date: dt.date | None = None, notes: str | None = None) -> InventoryLot:
    item = db.get(Item, item_id)
    if item is None:
        raise NotFound("Item")
    qty = _q(qty)
    _check_qty(item, qty)
    if item.current_released_revision_id is None:
        raise Conflict("Stock can only be received against an item with a released revision", "not_released")
    rev = db.get(ItemRevision, item.current_released_revision_id)
    assert rev is not None
    if rev.status not in ("Released", "NRND"):
        raise Conflict(f"Item revision {rev.revision_label} is {rev.status}; receipt blocked", "blocked_item")
    approved = db.execute(select(AmlEntry).where(AmlEntry.item_id == item.id, AmlEntry.status == "Approved")).scalars().all()
    if manufacturer_part_id:
        if manufacturer_part_id not in {a.manufacturer_part_id for a in approved}:
            raise Conflict("The manufacturer part is not an Approved AML entry for this item", "not_on_aml")
    elif approved:
        raise DomainError("This item has an approved AML: the manufacturer part received must be specified",
                          "mpn_required")
    loc = _location(db, location_id)
    lot = InventoryLot(lot_no=next_number(db, "LOT"), item_id=item.id, item_revision_id=rev.id,
                       manufacturer_part_id=manufacturer_part_id, supplier_name=supplier_name,
                       supplier_part_number=supplier_part_number, purchase_order_ref=purchase_order_ref,
                       supplier_lot=supplier_lot, manufacturer_lot=manufacturer_lot, date_code=date_code,
                       qty_received=qty, expiry_date=expiry_date, received_by=actor.user_id,
                       status="Pending Inspection", notes=notes)
    db.add(lot)
    db.flush()
    audit.record(db, actor, "create", "inventory_lot", lot.id, lot.lot_no,
                 after={"item": item.part_number, "revision": rev.revision_label, "qty_received": qty,
                        "location": loc.code, "manufacturer_part_id": manufacturer_part_id,
                        "supplier_name": supplier_name, "supplier_lot": supplier_lot,
                        "manufacturer_lot": manufacturer_lot, "date_code": date_code,
                        "purchase_order_ref": purchase_order_ref, "expiry_date": expiry_date})
    _post(db, actor, txn_type="RECEIPT", lot=lot, location_id=loc.id, d_on_hand=qty, d_reserved=Decimal(0),
          correlation_id=uuid.uuid4(), reference=purchase_order_ref, reason="Goods receipt")
    return lot


def inspect(db: Session, actor: Actor, lot_id: uuid.UUID, accept: bool, password: str, comment: str | None) -> None:
    lot, _ = _lock_lot(db, lot_id)
    if lot.status != "Pending Inspection":
        raise Conflict(f"Lot is {lot.status}, not awaiting inspection")
    meaning = "Material Released" if accept else "Material Rejected"
    sig = signatures.sign(db, actor, object_type="inventory_lot", object_id=lot.id, meaning=meaning,
                          password=password, comment=comment, label=lot.lot_no,
                          review_cycle=signatures.next_event_cycle(db, "inventory_lot", lot.id))
    _post_status(db, actor, lot, "INSPECTION_ACCEPT" if accept else "INSPECTION_REJECT",
                 "Available" if accept else "Quarantined",
                 "Incoming inspection accepted" if accept else "Incoming inspection rejected", comment, sig.id)


def issue(db: Session, actor: Actor, lot_id: uuid.UUID, location_id: uuid.UUID, qty: Any, reference: str,
          comment: str | None) -> StockTxn:
    lot, item = _lock_lot(db, lot_id)
    qty = _q(qty)
    _check_qty(item, qty)
    if not (reference or "").strip():
        raise DomainError("An issue reference (e.g. build or work order) is required", "validation")
    loc = _location(db, location_id, must_be_active=False)
    probs = usability_problems(db, lot, loc)
    if probs:
        raise Conflict("Lot cannot be issued: " + "; ".join(probs), "not_usable")
    return _post(db, actor, txn_type="ISSUE", lot=lot, location_id=loc.id, d_on_hand=-qty, d_reserved=Decimal(0),
                 correlation_id=uuid.uuid4(), reference=reference, comment=comment, reason="Issue")


def return_stock(db: Session, actor: Actor, lot_id: uuid.UUID, location_id: uuid.UUID, qty: Any, reference: str,
                 comment: str | None) -> StockTxn:
    lot, item = _lock_lot(db, lot_id)
    qty = _q(qty)
    _check_qty(item, qty)
    issued = db.execute(select(func.coalesce(func.sum(-StockTxn.d_on_hand), 0)).where(
        StockTxn.lot_id == lot.id, StockTxn.txn_type == "ISSUE")).scalar_one()
    returned = db.execute(select(func.coalesce(func.sum(StockTxn.d_on_hand), 0)).where(
        StockTxn.lot_id == lot.id, StockTxn.txn_type == "RETURN")).scalar_one()
    if qty > Decimal(issued) - Decimal(returned):
        raise Conflict(f"Cannot return more than was issued from this lot ({Decimal(issued) - Decimal(returned)})")
    loc = _location(db, location_id)
    return _post(db, actor, txn_type="RETURN", lot=lot, location_id=loc.id, d_on_hand=qty, d_reserved=Decimal(0),
                 correlation_id=uuid.uuid4(), reference=reference, comment=comment, reason="Return to stock")


def reserve(db: Session, actor: Actor, lot_id: uuid.UUID, location_id: uuid.UUID, qty: Any, reference: str,
            release: bool, comment: str | None) -> StockTxn:
    lot, item = _lock_lot(db, lot_id)
    qty = _q(qty)
    _check_qty(item, qty)
    if not (reference or "").strip():
        raise DomainError("A reservation reference is required", "validation")
    loc = _location(db, location_id, must_be_active=False)
    if not release:
        probs = usability_problems(db, lot, loc)
        if probs:
            raise Conflict("Lot cannot be reserved: " + "; ".join(probs), "not_usable")
    return _post(db, actor, txn_type="RESERVE_RELEASE" if release else "RESERVE", lot=lot, location_id=loc.id,
                 d_on_hand=Decimal(0), d_reserved=-qty if release else qty, correlation_id=uuid.uuid4(),
                 reference=reference, comment=comment, reason="Reservation release" if release else "Reservation")


def transfer(db: Session, actor: Actor, lot_id: uuid.UUID, from_id: uuid.UUID, to_id: uuid.UUID, qty: Any,
             comment: str | None) -> list[StockTxn]:
    lot, item = _lock_lot(db, lot_id)
    qty = _q(qty)
    _check_qty(item, qty)
    if from_id == to_id:
        raise DomainError("Source and destination are the same", "validation")
    src, dst = _location(db, from_id, must_be_active=False), _location(db, to_id)
    if src.is_quarantine and not dst.is_quarantine and lot.status == "Quarantined":
        raise Conflict("Quarantined material must be released before leaving a quarantine location")
    cid = uuid.uuid4()
    a, b = sorted([src.id, dst.id])  # deterministic balance lock order
    for lid in (a, b):
        db.execute(pg_insert(LotBalance).values(lot_id=lot.id, location_id=lid, qty_on_hand=0, qty_reserved=0)
                   .on_conflict_do_nothing())
        db.execute(select(LotBalance).where(LotBalance.lot_id == lot.id, LotBalance.location_id == lid).with_for_update())
    out = _post(db, actor, txn_type="TRANSFER_OUT", lot=lot, location_id=src.id, d_on_hand=-qty, d_reserved=Decimal(0),
                correlation_id=cid, comment=comment, reason=f"Transfer to {dst.code}")
    inn = _post(db, actor, txn_type="TRANSFER_IN", lot=lot, location_id=dst.id, d_on_hand=qty, d_reserved=Decimal(0),
                correlation_id=cid, comment=comment, reason=f"Transfer from {src.code}")
    return [out, inn]


def adjust(db: Session, actor: Actor, lot_id: uuid.UUID, location_id: uuid.UUID, delta: Any, reason: str,
           comment: str | None, corrects_txn_id: int | None) -> StockTxn:
    lot, item = _lock_lot(db, lot_id)
    delta = _q(delta)
    _check_qty(item, delta, allow_negative=True)
    if not (reason or "").strip():
        raise DomainError("A reason is required for adjustments", "validation")
    if corrects_txn_id is not None:
        orig = db.get(StockTxn, corrects_txn_id)
        if orig is None or orig.lot_id != lot.id:
            raise DomainError("The corrected transaction does not belong to this lot", "validation")
    loc = _location(db, location_id, must_be_active=False)
    return _post(db, actor, txn_type="ADJUST", lot=lot, location_id=loc.id, d_on_hand=delta, d_reserved=Decimal(0),
                 correlation_id=uuid.uuid4(), reason=reason, comment=comment, corrects_txn_id=corrects_txn_id)


def scrap(db: Session, actor: Actor, lot_id: uuid.UUID, location_id: uuid.UUID, qty: Any, reason: str,
          comment: str | None) -> StockTxn:
    lot, item = _lock_lot(db, lot_id)
    qty = _q(qty)
    _check_qty(item, qty)
    if not (reason or "").strip():
        raise DomainError("A reason is required for scrap", "validation")
    loc = _location(db, location_id, must_be_active=False)
    return _post(db, actor, txn_type="SCRAP", lot=lot, location_id=loc.id, d_on_hand=-qty, d_reserved=Decimal(0),
                 correlation_id=uuid.uuid4(), reason=reason, comment=comment)


def quarantine(db: Session, actor: Actor, lot_id: uuid.UUID, reason: str, comment: str | None) -> None:
    lot, _ = _lock_lot(db, lot_id)
    if lot.status == "Quarantined":
        raise Conflict("Lot is already quarantined")
    if not (reason or "").strip():
        raise DomainError("A quarantine reason is required (e.g. NCR reference)", "validation")
    _post_status(db, actor, lot, "QUARANTINE", "Quarantined", reason, comment)


def release_quarantine(db: Session, actor: Actor, lot_id: uuid.UUID, password: str, comment: str | None) -> None:
    lot, _ = _lock_lot(db, lot_id)
    if lot.status != "Quarantined":
        raise Conflict("Lot is not quarantined")
    if not (comment or "").strip():
        raise DomainError("A disposition comment is required to release from quarantine", "comment_required")
    sig = signatures.sign(db, actor, object_type="inventory_lot", object_id=lot.id, meaning="Material Released",
                          password=password, comment=comment, label=lot.lot_no,
                          review_cycle=signatures.next_event_cycle(db, "inventory_lot", lot.id))
    _post_status(db, actor, lot, "QUARANTINE_RELEASE", "Available", "Released from quarantine", comment, sig.id)


# ---------------- queries ----------------

def _txn_rows(rows: list) -> list[dict[str, Any]]:  # type: ignore[type-arg]
    return [{"id": t.id, "txn_type": t.txn_type, "occurred_at": t.occurred_at, "lot_id": str(t.lot_id),
             "lot_no": lot_no, "part_number": pn, "item_id": str(t.item_id), "location": code,
             "d_on_hand": float(t.d_on_hand), "d_reserved": float(t.d_reserved),
             "on_hand_before": float(t.on_hand_before), "on_hand_after": float(t.on_hand_after),
             "reserved_before": float(t.reserved_before), "reserved_after": float(t.reserved_after),
             "reason": t.reason, "comment": t.comment, "reference": t.reference, "by": by,
             "corrects_txn_id": t.corrects_txn_id, "correlation_id": str(t.correlation_id)}
            for t, lot_no, pn, code, by in rows]


def ledger(db: Session, lot_id: uuid.UUID | None = None, item_id: uuid.UUID | None = None,
           txn_type: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    q = (select(StockTxn, InventoryLot.lot_no, Item.part_number, Location.code, User.full_name)
         .join(InventoryLot, InventoryLot.id == StockTxn.lot_id).join(Item, Item.id == StockTxn.item_id)
         .outerjoin(Location, Location.id == StockTxn.location_id).join(User, User.id == StockTxn.actor_id))
    if lot_id:
        q = q.where(StockTxn.lot_id == lot_id)
    if item_id:
        q = q.where(StockTxn.item_id == item_id)
    if txn_type:
        q = q.where(StockTxn.txn_type == txn_type)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(StockTxn.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": _txn_rows(rows)}


def list_lots(db: Session, q: str | None, status: str | None, item_id: uuid.UUID | None, include_empty: bool,
              limit: int, offset: int) -> dict[str, Any]:
    tot = (select(LotBalance.lot_id, func.sum(LotBalance.qty_on_hand).label("oh"),
                  func.sum(LotBalance.qty_reserved).label("rs")).group_by(LotBalance.lot_id).subquery())
    base = (select(InventoryLot, Item.part_number, ItemRevision.description, ItemRevision.revision_label, Item.uom,
                   tot.c.oh, tot.c.rs, ManufacturerPart.mpn, Manufacturer.name)
            .join(Item, Item.id == InventoryLot.item_id)
            .join(ItemRevision, ItemRevision.id == InventoryLot.item_revision_id)
            .outerjoin(tot, tot.c.lot_id == InventoryLot.id)
            .outerjoin(ManufacturerPart, ManufacturerPart.id == InventoryLot.manufacturer_part_id)
            .outerjoin(Manufacturer, Manufacturer.id == ManufacturerPart.manufacturer_id))
    if q:
        like = f"%{q}%"
        base = base.where(or_(InventoryLot.lot_no.ilike(like), Item.part_number.ilike(like),
                              InventoryLot.supplier_lot.ilike(like), InventoryLot.manufacturer_lot.ilike(like),
                              InventoryLot.date_code.ilike(like), ManufacturerPart.mpn.ilike(like)))
    if status:
        base = base.where(InventoryLot.status == status)
    if item_id:
        base = base.where(InventoryLot.item_id == item_id)
    if not include_empty:
        base = base.where(and_(tot.c.oh.is_not(None), tot.c.oh > 0))
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(InventoryLot.received_at.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [
        {"id": str(l.id), "lot_no": l.lot_no, "status": l.status, "part_number": pn, "item_id": str(l.item_id),
         "description": desc, "revision": revl, "uom": uom, "qty_received": float(l.qty_received),
         "qty_on_hand": float(oh or 0), "qty_reserved": float(rs or 0), "manufacturer": mname, "mpn": mpn,
         "supplier_name": l.supplier_name, "supplier_lot": l.supplier_lot, "date_code": l.date_code,
         "expiry_date": l.expiry_date, "received_at": l.received_at}
        for l, pn, desc, revl, uom, oh, rs, mpn, mname in rows]}


def lot_detail(db: Session, lot_id: uuid.UUID) -> dict[str, Any]:
    lot = db.get(InventoryLot, lot_id)
    if lot is None:
        raise NotFound("Lot")
    item = db.get(Item, lot.item_id)
    rev = db.get(ItemRevision, lot.item_revision_id)
    assert item and rev
    mp = db.get(ManufacturerPart, lot.manufacturer_part_id) if lot.manufacturer_part_id else None
    mname = db.get(Manufacturer, mp.manufacturer_id).name if mp else None  # type: ignore[union-attr]
    bals = db.execute(select(LotBalance, Location).join(Location, Location.id == LotBalance.location_id)
                      .where(LotBalance.lot_id == lot.id).order_by(Location.code)).all()
    atts = db.execute(select(Attachment, FileObject).join(FileObject, FileObject.id == Attachment.file_object_id)
                      .where(Attachment.object_type == "inventory_lot", Attachment.object_id == lot.id)).all()
    receiver = db.get(User, lot.received_by)
    return {
        "id": str(lot.id), "lot_no": lot.lot_no, "status": lot.status, "item_id": str(item.id),
        "part_number": item.part_number, "description": rev.description, "revision": rev.revision_label,
        "revision_status": rev.status, "uom": item.uom, "manufacturer": mname, "mpn": mp.mpn if mp else None,
        "supplier_name": lot.supplier_name, "supplier_part_number": lot.supplier_part_number,
        "purchase_order_ref": lot.purchase_order_ref, "supplier_lot": lot.supplier_lot,
        "manufacturer_lot": lot.manufacturer_lot, "date_code": lot.date_code,
        "qty_received": float(lot.qty_received), "expiry_date": lot.expiry_date, "received_at": lot.received_at,
        "received_by": receiver.full_name if receiver else None, "notes": lot.notes,
        "usability_problems": usability_problems(db, lot),
        "balances": [{"location_id": str(l.id), "location_code": l.code, "location_name": l.path,
                      "is_quarantine": l.is_quarantine, "qty_on_hand": float(b.qty_on_hand),
                      "qty_reserved": float(b.qty_reserved), "qty_available": float(b.qty_on_hand - b.qty_reserved)}
                     for b, l in bals if b.qty_on_hand > 0 or b.qty_reserved > 0],
        "qty_on_hand": float(sum((b.qty_on_hand for b, _ in bals), Decimal(0))),
        "signatures": signatures.list_for(db, "inventory_lot", lot.id),
        "transactions": ledger(db, lot_id=lot.id, limit=500)["items"],
        "attachments": [{"id": str(a.id), "filename": a.filename, "doc_kind": a.doc_kind, "sha256": f.sha256,
                         "size_bytes": f.size_bytes, "uploaded_at": a.uploaded_at} for a, f in atts],
    }


def verify_balances(db: Session) -> dict[str, Any]:
    """Rebuild balances from the ledger and compare with the projection."""
    ledger_tot = {(l, loc): (oh, rs) for l, loc, oh, rs in db.execute(
        select(StockTxn.lot_id, StockTxn.location_id, func.sum(StockTxn.d_on_hand), func.sum(StockTxn.d_reserved))
        .where(StockTxn.location_id.is_not(None)).group_by(StockTxn.lot_id, StockTxn.location_id))}
    mismatches = []
    for b in db.execute(select(LotBalance)).scalars():
        oh, rs = ledger_tot.pop((b.lot_id, b.location_id), (0, 0))
        if Decimal(oh) != Decimal(b.qty_on_hand) or Decimal(rs) != Decimal(b.qty_reserved):
            mismatches.append({"lot_id": str(b.lot_id), "location_id": str(b.location_id),
                               "projection": [float(b.qty_on_hand), float(b.qty_reserved)],
                               "ledger": [float(oh), float(rs)]})
    for (l, loc), (oh, rs) in ledger_tot.items():
        mismatches.append({"lot_id": str(l), "location_id": str(loc), "projection": None, "ledger": [float(oh), float(rs)]})
    return {"ok": not mismatches, "mismatches": mismatches}
