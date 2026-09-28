import csv
import datetime as dt
import io
import json
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import AmlEntry, AuditEvent, InventoryLot, Item, ItemRevision, Location, ManufacturerPart
from app.services.inventory import ledger
from app.services.items import stock_summary


def dashboard(db: Session) -> dict[str, Any]:
    cur = select(Item.id, ItemRevision.status).join(ItemRevision, ItemRevision.id == Item.current_released_revision_id).subquery()
    by_status = dict(db.execute(select(cur.c.status, func.count()).group_by(cur.c.status)).all())
    total_items = db.execute(select(func.count()).select_from(Item)).scalar_one()
    unreleased = db.execute(select(func.count()).select_from(Item).where(Item.current_released_revision_id.is_(None))).scalar_one()
    pending = db.execute(select(func.count()).select_from(ItemRevision)
                         .where(ItemRevision.status.in_(("Under Review", "Approved")))).scalar_one()
    pending_aml = db.execute(select(func.count()).select_from(AmlEntry).where(AmlEntry.status == "Proposed")).scalar_one()
    lots_pending = db.execute(select(func.count()).select_from(InventoryLot)
                              .where(InventoryLot.status == "Pending Inspection")).scalar_one()
    lots_q = db.execute(select(func.count()).select_from(InventoryLot).where(InventoryLot.status == "Quarantined")).scalar_one()
    released_ids = list(db.execute(select(Item.id).join(ItemRevision, ItemRevision.id == Item.current_released_revision_id)
                                   .where(ItemRevision.status.in_(("Released", "NRND")))).scalars())
    stock = stock_summary(db, released_ids)
    mins = dict(db.execute(select(Item.id, Item.min_stock).where(Item.id.in_(released_ids))).all()) if released_ids else {}
    out_of_stock = sum(1 for i in released_ids if stock[i]["available"] <= 0)
    low = sum(1 for i in released_ids if 0 < stock[i]["available"] < float(mins.get(i) or 0))
    recent_audit = db.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(10)).scalars()
    recent_changes = db.execute(
        select(ItemRevision, Item.part_number).join(Item, Item.id == ItemRevision.item_id)
        .order_by(ItemRevision.modified_at.desc()).limit(8)).all()
    return {
        "parts_total": total_items,
        "parts_active": by_status.get("Released", 0),
        "parts_nrnd": by_status.get("NRND", 0),
        "parts_obsolete": by_status.get("Obsolete", 0) + by_status.get("Prohibited", 0),
        "parts_unreleased": unreleased,
        "pending_approvals": pending + pending_aml,
        "lots_pending_inspection": lots_pending,
        "lots_quarantined": lots_q,
        "low_stock": low,
        "out_of_stock": out_of_stock,
        "locations": db.execute(select(func.count()).select_from(Location).where(Location.is_active)).scalar_one(),
        "recent_transactions": ledger(db, limit=8)["items"],
        "recent_changes": [{"item_id": str(r.item_id), "part_number": pn, "revision": r.revision_label,
                            "status": r.status, "description": r.description, "modified_at": r.modified_at}
                           for r, pn in recent_changes],
        "recent_audit": [{"id": e.id, "occurred_at": e.occurred_at, "actor": e.actor_username, "action": e.action,
                          "entity_type": e.entity_type, "entity_label": e.entity_label} for e in recent_audit],
    }


def search(db: Session, q: str, limit: int = 8) -> list[dict[str, Any]]:
    like = f"%{q.strip()}%"
    out: list[dict[str, Any]] = []
    latest = (select(ItemRevision.item_id, func.max(ItemRevision.created_at).label("mx"))
              .group_by(ItemRevision.item_id).subquery())
    mpn_items = (select(AmlEntry.item_id).join(ManufacturerPart, ManufacturerPart.id == AmlEntry.manufacturer_part_id)
                 .where(ManufacturerPart.mpn.ilike(like)))
    for i, r in db.execute(
        select(Item, ItemRevision).join(latest, latest.c.item_id == Item.id)
        .join(ItemRevision, (ItemRevision.item_id == Item.id) & (ItemRevision.created_at == latest.c.mx))
        .where(or_(Item.part_number.ilike(like), ItemRevision.description.ilike(like),
                   ItemRevision.value.ilike(like), Item.id.in_(mpn_items))).limit(limit)
    ).all():
        out.append({"type": "Part", "id": str(i.id), "title": i.part_number, "subtitle": r.description,
                    "url": f"/parts/{i.id}"})
    for l, pn in db.execute(select(InventoryLot, Item.part_number).join(Item, Item.id == InventoryLot.item_id).where(
            or_(InventoryLot.lot_no.ilike(like), InventoryLot.supplier_lot.ilike(like),
                InventoryLot.manufacturer_lot.ilike(like), InventoryLot.purchase_order_ref.ilike(like))).limit(limit)).all():
        out.append({"type": "Lot", "id": str(l.id), "title": l.lot_no, "subtitle": f"{pn} · {l.status}",
                    "url": f"/lots/{l.id}"})
    for loc in db.execute(select(Location).where(or_(Location.code.ilike(like), Location.name.ilike(like)))
                          .limit(limit)).scalars():
        out.append({"type": "Location", "id": str(loc.id), "title": loc.code, "subtitle": loc.path,
                    "url": f"/locations/{loc.id}"})
    return out


def audit_query(entity_type: str | None, entity_id: str | None, actor: str | None, action: str | None,
                date_from: dt.date | None, date_to: dt.date | None) -> Select:
    q = select(AuditEvent)
    if entity_type:
        q = q.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if actor:
        q = q.where(AuditEvent.actor_username.ilike(f"%{actor}%"))
    if action:
        q = q.where(AuditEvent.action == action)
    if date_from:
        q = q.where(AuditEvent.occurred_at >= dt.datetime.combine(date_from, dt.time.min, dt.timezone.utc))
    if date_to:
        q = q.where(AuditEvent.occurred_at < dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min,
                                                                 dt.timezone.utc))
    return q


def audit_dict(e: AuditEvent) -> dict[str, Any]:
    return {"id": e.id, "event_uuid": str(e.event_uuid), "occurred_at": e.occurred_at, "actor": e.actor_username,
            "action": e.action, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "entity_label": e.entity_label, "before": e.before, "after": e.after, "reason": e.reason, "ip": e.ip,
            "session_id": str(e.session_id) if e.session_id else None, "request_id": e.request_id, "hash": e.hash}


def audit_csv(rows: list[AuditEvent]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "occurred_at_utc", "actor", "action", "entity_type", "entity_id", "entity_label", "before",
                "after", "reason", "ip", "session_id", "request_id", "prev_hash", "hash"])
    for e in rows:
        w.writerow([e.id, e.occurred_at.isoformat(), e.actor_username, e.action, e.entity_type, e.entity_id,
                    e.entity_label, json.dumps(e.before) if e.before else "", json.dumps(e.after) if e.after else "",
                    e.reason or "", e.ip or "", e.session_id or "", e.request_id or "", e.prev_hash, e.hash])
    return buf.getvalue()

