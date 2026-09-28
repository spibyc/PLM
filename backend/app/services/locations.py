import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.errors import Conflict, DomainError, NotFound
from app.models import InventoryLot, Item, ItemRevision, Location, LotBalance, StockTxn, User
from app.models.locations import LOCATION_KINDS
from app.services import audit


def create_location(db: Session, actor: Actor, parent_id: uuid.UUID | None, kind: str, segment: str, name: str,
                    is_quarantine: bool, notes: str | None) -> Location:
    if kind not in LOCATION_KINDS:
        raise DomainError("Invalid location kind", "validation")
    segment = segment.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,16}", segment):
        raise DomainError("Code segment must be 1-16 letters/digits", "validation")
    parent = None
    if parent_id:
        parent = db.get(Location, parent_id)
        if parent is None:
            raise NotFound("Parent location")
        if LOCATION_KINDS.index(kind) <= LOCATION_KINDS.index(parent.kind):
            raise DomainError(f"A {kind} cannot be placed inside a {parent.kind}", "hierarchy")
        if not parent.is_active:
            raise DomainError("Parent location is inactive", "validation")
    elif kind != "site":
        raise DomainError("Top-level locations must be sites", "hierarchy")
    code = f"{parent.code}-{segment}" if parent else segment
    if db.execute(select(Location).where(Location.code == code)).scalar_one_or_none():
        raise Conflict(f"Location code {code} already exists")
    loc = Location(parent_id=parent.id if parent else None, kind=kind, code=code, name=name.strip(),
                   path=f"{parent.path} / {name.strip()}" if parent else name.strip(),
                   is_quarantine=is_quarantine or bool(parent and parent.is_quarantine), notes=notes,
                   created_by=actor.user_id, is_active=True)
    db.add(loc)
    db.flush()
    audit.record(db, actor, "create", "location", loc.id, code,
                 after={"code": code, "kind": kind, "name": loc.name, "is_quarantine": loc.is_quarantine})
    return loc


def update_location(db: Session, actor: Actor, loc_id: uuid.UUID, name: str | None, is_active: bool | None,
                    notes: str | None, reason: str) -> Location:
    loc = db.get(Location, loc_id, with_for_update=True)
    if loc is None:
        raise NotFound("Location")
    before = {"name": loc.name, "is_active": loc.is_active, "notes": loc.notes}
    if is_active is False and loc.is_active:
        held = db.execute(select(func.coalesce(func.sum(LotBalance.qty_on_hand), 0))
                          .where(LotBalance.location_id == loc.id)).scalar_one()
        kids = db.execute(select(func.count()).select_from(Location)
                          .where(Location.parent_id == loc.id, Location.is_active)).scalar_one()
        if held > 0 or kids > 0:
            raise Conflict("Cannot deactivate a location holding stock or active sub-locations")
    if name is not None:
        loc.name = name.strip()
    if is_active is not None:
        loc.is_active = is_active
    if notes is not None:
        loc.notes = notes
    after = {"name": loc.name, "is_active": loc.is_active, "notes": loc.notes}
    b, a = audit.diff(before, after)
    if a:
        audit.record(db, actor, "modify", "location", loc.id, loc.code, before=b, after=a, reason=reason)
    return loc


def loc_dict(loc: Location) -> dict[str, Any]:
    return {"id": str(loc.id), "parent_id": str(loc.parent_id) if loc.parent_id else None, "kind": loc.kind,
            "code": loc.code, "name": loc.name, "path": loc.path, "is_quarantine": loc.is_quarantine,
            "is_active": loc.is_active, "notes": loc.notes}


def list_locations(db: Session) -> list[dict[str, Any]]:
    totals = dict(db.execute(select(LotBalance.location_id, func.sum(LotBalance.qty_on_hand))
                             .group_by(LotBalance.location_id)).all())
    return [{**loc_dict(l), "qty_on_hand": float(totals.get(l.id, 0) or 0)}
            for l in db.execute(select(Location).order_by(Location.code)).scalars()]


def location_detail(db: Session, loc_id: uuid.UUID | None = None, code: str | None = None) -> dict[str, Any]:
    q = select(Location).where(Location.id == loc_id) if loc_id else select(Location).where(Location.code == code)
    loc = db.execute(q).scalar_one_or_none()
    if loc is None:
        raise NotFound("Location")
    stock = db.execute(
        select(LotBalance, InventoryLot, Item, ItemRevision)
        .join(InventoryLot, InventoryLot.id == LotBalance.lot_id)
        .join(Item, Item.id == InventoryLot.item_id)
        .join(ItemRevision, ItemRevision.id == InventoryLot.item_revision_id)
        .where(LotBalance.location_id == loc.id, LotBalance.qty_on_hand > 0).order_by(Item.part_number)
    ).all()
    moves = db.execute(
        select(StockTxn, InventoryLot.lot_no, Item.part_number, User.full_name)
        .join(InventoryLot, InventoryLot.id == StockTxn.lot_id).join(Item, Item.id == StockTxn.item_id)
        .join(User, User.id == StockTxn.actor_id)
        .where(StockTxn.location_id == loc.id).order_by(StockTxn.id.desc()).limit(25)
    ).all()
    children = db.execute(select(Location).where(Location.parent_id == loc.id).order_by(Location.code)).scalars()
    chain = []
    p = loc
    while p.parent_id:
        p = db.get(Location, p.parent_id)  # type: ignore[assignment]
        chain.insert(0, {"id": str(p.id), "code": p.code, "name": p.name})
    return {
        **loc_dict(loc), "ancestors": chain, "children": [loc_dict(c) for c in children],
        "stock": [{"lot_id": str(l.id), "lot_no": l.lot_no, "lot_status": l.status, "item_id": str(i.id),
                   "part_number": i.part_number, "description": r.description, "revision": r.revision_label,
                   "qty_on_hand": float(b.qty_on_hand), "qty_reserved": float(b.qty_reserved),
                   "qty_available": float(b.qty_on_hand - b.qty_reserved), "uom": i.uom,
                   "expiry_date": l.expiry_date} for b, l, i, r in stock],
        "recent_movements": [{"id": t.id, "txn_type": t.txn_type, "occurred_at": t.occurred_at, "lot_no": lot_no,
                              "part_number": pn, "d_on_hand": float(t.d_on_hand), "by": by, "reason": t.reason}
                             for t, lot_no, pn, by in moves],
    }
