import hashlib
import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.config import get_settings
from app.core.errors import Conflict, DomainError, Forbidden, NotFound
from app.models import (
    AmlEntry, Attachment, FileObject, Item, ItemRevision, LotBalance, InventoryLot, Manufacturer,
    ManufacturerPart, DistributorSource, Signature, User,
)
from app.services import audit, signatures
from app.services.audit import canonical
from app.services.numbering import next_number

CONTENT_FIELDS = ("description", "category", "subcategory", "component_type", "value", "package",
                  "rohs_status", "reach_status", "notes", "change_reason")
LABELS = [c for c in "ABCDEFGHJKLMNPRTUVWY"]  # skips I, O, Q, S, X, Z


def next_label(existing: list[str]) -> str:
    seq = LABELS + [a + b for a in LABELS for b in LABELS]
    for lab in seq:
        if lab not in existing:
            return lab
    raise DomainError("Revision label space exhausted")


def _rev_content(db: Session, rev: ItemRevision) -> dict[str, Any]:
    files = db.execute(select(Attachment.filename, Attachment.doc_kind, FileObject.sha256)
                       .join(FileObject, FileObject.id == Attachment.file_object_id)
                       .where(Attachment.object_type == "item_revision", Attachment.object_id == rev.id)).all()
    return {
        "item_id": str(rev.item_id), "revision": rev.revision_label,
        **{f: getattr(rev, f) for f in CONTENT_FIELDS},
        "files": sorted([f"{n}|{k}|{h}" for n, k, h in files]),
    }


def content_hash(db: Session, rev: ItemRevision) -> str:
    return hashlib.sha256(canonical(_rev_content(db, rev)).encode()).hexdigest()


def _get_item(db: Session, item_id: uuid.UUID, lock: bool = False) -> Item:
    q = select(Item).where(Item.id == item_id)
    if lock:
        q = q.with_for_update()
    item = db.execute(q).scalar_one_or_none()
    if item is None:
        raise NotFound("Item")
    return item


def _get_rev(db: Session, item: Item, rev_id: uuid.UUID, lock: bool = True) -> ItemRevision:
    q = select(ItemRevision).where(ItemRevision.id == rev_id, ItemRevision.item_id == item.id)
    if lock:
        q = q.with_for_update()
    rev = db.execute(q).scalar_one_or_none()
    if rev is None:
        raise NotFound("Revision")
    return rev


def _label(item: Item, rev: ItemRevision) -> str:
    return f"{item.part_number} rev {rev.revision_label}"


def create_item(db: Session, actor: Actor, item_class: str, uom: str, content: dict[str, Any],
                min_stock: float = 0) -> Item:
    pn = next_number(db, "PART")
    item = Item(part_number=pn, item_class=item_class, uom=uom, created_by=actor.user_id, min_stock=min_stock)
    db.add(item)
    db.flush()
    rev = ItemRevision(item_id=item.id, revision_label="A", status="Draft", created_by=actor.user_id,
                       modified_by=actor.user_id, review_cycle=0, row_version=1,
                       **{f: content.get(f) for f in CONTENT_FIELDS})
    db.add(rev)
    db.flush()
    audit.record(db, actor, "create", "item", item.id, pn,
                 after={"part_number": pn, "item_class": item_class, "uom": uom, "min_stock": min_stock})
    audit.record(db, actor, "create", "item_revision", rev.id, _label(item, rev),
                 after={f: getattr(rev, f) for f in CONTENT_FIELDS})
    return item


def update_planning(db: Session, actor: Actor, item_id: uuid.UUID, min_stock: float, reason: str) -> None:
    item = _get_item(db, item_id, lock=True)
    before = {"min_stock": str(item.min_stock)}
    item.min_stock = min_stock
    audit.record(db, actor, "modify", "item", item.id, item.part_number, before=before,
                 after={"min_stock": str(min_stock)}, reason=reason)


def edit_draft(db: Session, actor: Actor, item_id: uuid.UUID, rev_id: uuid.UUID, row_version: int,
               changes: dict[str, Any]) -> ItemRevision:
    item = _get_item(db, item_id)
    rev = _get_rev(db, item, rev_id)
    if rev.status != "Draft":
        raise Conflict(f"Revision is {rev.status}; only Draft revisions can be edited", "locked")
    if rev.row_version != row_version:
        raise Conflict("This revision was modified by someone else. Reload and re-apply your changes.", "stale")
    before = {f: getattr(rev, f) for f in CONTENT_FIELDS}
    for f in CONTENT_FIELDS:
        if f in changes:
            setattr(rev, f, changes[f])
    after = {f: getattr(rev, f) for f in CONTENT_FIELDS}
    b, a = audit.diff(before, after)
    if a:
        rev.row_version += 1
        rev.modified_by = actor.user_id
        rev.modified_at = func.clock_timestamp()
        audit.record(db, actor, "modify", "item_revision", rev.id, _label(item, rev), before=b, after=a)
    db.flush()
    return rev



def admin_edit_revision(db: Session, actor: Actor, item_id: uuid.UUID, rev_id: uuid.UUID, row_version: int,
                        changes: dict[str, Any], reason: str) -> ItemRevision:
    """Superuser correction of any item revision, including released history.

    The audit chain remains immutable and records the previous and replacement values.
    """
    if not actor.has("admin:override"):
        raise Forbidden("Administrator superuser permission required")
    if len((reason or "").strip()) < 3:
        raise DomainError("A reason is required for a superuser correction", "validation")
    item = _get_item(db, item_id, lock=True)
    rev = _get_rev(db, item, rev_id)
    if rev.row_version != row_version:
        raise Conflict("This revision was modified by someone else. Reload and re-apply your changes.", "stale")
    before = {f: getattr(rev, f) for f in CONTENT_FIELDS}
    db.execute(text("SET LOCAL qplm.admin_override = 'on'"))
    for f in CONTENT_FIELDS:
        if f in changes:
            setattr(rev, f, changes[f])
    rev.row_version += 1
    rev.modified_by = actor.user_id
    rev.modified_at = func.clock_timestamp()
    db.flush()
    # A historical correction invalidates the old signed content hash. Keep signatures as historical
    # evidence and replace the revision hash with the corrected content hash.
    rev.content_hash = content_hash(db, rev) if rev.status != "Draft" else None
    db.flush()
    after = {f: getattr(rev, f) for f in CONTENT_FIELDS}
    b, a = audit.diff(before, after)
    audit.record(db, actor, "admin_override_modify", "item_revision", rev.id, _label(item, rev),
                 before=b or before, after=a or after, reason=reason)
    return rev


def admin_delete_item(db: Session, actor: Actor, item_id: uuid.UUID, reason: str) -> str:
    """Permanently delete an item that is not referenced by inventory/procurement/BOM genealogy.

    Signatures/transitions/attachments belonging only to the part are purged. The hash-chained audit
    event is deliberately retained as evidence of the superuser purge.
    """
    if not actor.has("admin:override"):
        raise Forbidden("Administrator superuser permission required")
    if len((reason or "").strip()) < 3:
        raise DomainError("A reason is required for permanent deletion", "validation")
    item = _get_item(db, item_id, lock=True)
    label = item.part_number
    # Let PostgreSQL FKs prevent deletion when the part participates in procurement, stock, BOMs or builds.
    rev_ids = list(db.execute(select(ItemRevision.id).where(ItemRevision.item_id == item.id)).scalars())
    before = {"part_number": item.part_number, "revision_ids": [str(x) for x in rev_ids]}
    audit.record(db, actor, "admin_permanent_delete", "item", item.id, label, before=before, reason=reason)
    db.execute(text("SET LOCAL qplm.admin_override = 'on'"))
    if rev_ids:
        db.execute(delete(Signature).where(Signature.object_type == "item_revision", Signature.object_id.in_(rev_ids)))
        from app.models import StateTransition
        db.execute(delete(StateTransition).where(StateTransition.object_type == "item_revision", StateTransition.object_id.in_(rev_ids)))
        db.execute(delete(Attachment).where(Attachment.object_type == "item_revision", Attachment.object_id.in_(rev_ids)))
    db.execute(delete(AmlEntry).where(AmlEntry.item_id == item.id))
    item.current_released_revision_id = None
    db.flush()
    db.execute(delete(ItemRevision).where(ItemRevision.item_id == item.id))
    db.delete(item)
    db.flush()
    return label

def submit(db: Session, actor: Actor, item_id: uuid.UUID, rev_id: uuid.UUID) -> None:
    item = _get_item(db, item_id)
    rev = _get_rev(db, item, rev_id)
    if rev.status != "Draft":
        raise Conflict(f"Only Draft revisions can be submitted (is {rev.status})")
    if not (rev.description or "").strip():
        raise DomainError("Description is required", "validation")
    if rev.supersedes_id and not (rev.change_reason or "").strip():
        raise DomainError("A change reason is required for a new revision", "validation")
    rev.content_hash = content_hash(db, rev)
    rev.review_cycle += 1
    rev.status = "Under Review"
    rev.submitted_at = func.clock_timestamp()
    db.flush()
    signatures.transition(db, actor, "item_revision", rev.id, "Draft", "Under Review", label=_label(item, rev))


def sign(db: Session, actor: Actor, item_id: uuid.UUID, rev_id: uuid.UUID, meaning: str, password: str,
         comment: str | None, shown_hash: str | None) -> dict[str, Any]:
    item = _get_item(db, item_id, lock=True)
    rev = _get_rev(db, item, rev_id)
    label = _label(item, rev)
    allowed = {
        "Under Review": {"Engineering Approved", "Quality Approved", "Rejected"},
        "Approved": {"Released for Production", "Rejected"},
        "Released": {"NRND Approved", "Obsolescence Approved", "Prohibition Approved"},
        "NRND": {"Obsolescence Approved", "Prohibition Approved"},
        "Prohibited": {"Obsolescence Approved"},
    }.get(rev.status, set())
    if meaning not in allowed:
        raise Conflict(f"'{meaning}' cannot be applied to a revision in status {rev.status}", "bad_state")
    current = content_hash(db, rev) if rev.status in ("Under Review", "Approved") else rev.content_hash
    if rev.status in ("Under Review", "Approved") and current != rev.content_hash:
        raise Conflict("Content hash mismatch: the record changed after submission. Signing blocked.", "hash_mismatch")
    if shown_hash and shown_hash != rev.content_hash:
        raise Conflict("The content you reviewed is not the current content. Reload before signing.", "hash_mismatch")
    if (get_settings().enforce_separation_of_duties
            and meaning in ("Engineering Approved", "Quality Approved", "Released for Production")
            and actor.user_id in (rev.created_by, rev.modified_by)):
        raise Forbidden("Separation of duties: the author of a revision cannot approve or release it", "sod")
    sig = signatures.sign(db, actor, object_type="item_revision", object_id=rev.id, meaning=meaning,
                          password=password, comment=comment, review_cycle=rev.review_cycle,
                          content_hash=rev.content_hash, label=label)
    frm = rev.status
    if meaning == "Rejected":
        rev.status = "Draft"
        rev.row_version += 1
        signatures.transition(db, actor, "item_revision", rev.id, frm, "Draft", comment, sig.id, label)
    elif rev.status == "Under Review":
        have = set(db.execute(select(Signature.meaning).where(
            Signature.object_type == "item_revision", Signature.object_id == rev.id,
            Signature.review_cycle == rev.review_cycle, Signature.content_hash == rev.content_hash)).scalars())
        if {"Engineering Approved", "Quality Approved"} <= have:
            rev.status = "Approved"
            rev.approved_at = func.clock_timestamp()
            signatures.transition(db, actor, "item_revision", rev.id, frm, "Approved",
                                  "Approval rule satisfied (Engineering + Quality)", sig.id, label)
    elif meaning == "Released for Production":
        prev = db.get(ItemRevision, item.current_released_revision_id) if item.current_released_revision_id else None
        if prev is not None:
            prev_status = prev.status
            prev.status = "Superseded"
            db.flush()
            signatures.transition(db, actor, "item_revision", prev.id, prev_status, "Superseded",
                                  f"Superseded by rev {rev.revision_label}", sig.id, _label(item, prev))
        rev.status = "Released"
        rev.released_at = func.clock_timestamp()
        db.flush()
        item.current_released_revision_id = rev.id
        signatures.transition(db, actor, "item_revision", rev.id, frm, "Released", comment, sig.id, label)
    else:
        to = {"NRND Approved": "NRND", "Obsolescence Approved": "Obsolete", "Prohibition Approved": "Prohibited"}[meaning]
        rev.status = to
        signatures.transition(db, actor, "item_revision", rev.id, frm, to, comment, sig.id, label)
    db.flush()
    return {"status": rev.status}


def new_revision(db: Session, actor: Actor, item_id: uuid.UUID, change_reason: str) -> ItemRevision:
    item = _get_item(db, item_id, lock=True)
    revs = db.execute(select(ItemRevision).where(ItemRevision.item_id == item.id)).scalars().all()
    if any(r.status in ("Draft", "Under Review", "Approved") for r in revs):
        raise Conflict("An open revision already exists for this item")
    if item.current_released_revision_id is None:
        raise Conflict("There is no released revision to revise")
    base = db.get(ItemRevision, item.current_released_revision_id)
    assert base is not None
    rev = ItemRevision(item_id=item.id, revision_label=next_label([r.revision_label for r in revs]), status="Draft",
                       created_by=actor.user_id, modified_by=actor.user_id, supersedes_id=base.id, review_cycle=0,
                       row_version=1, **{f: getattr(base, f) for f in CONTENT_FIELDS if f != "change_reason"},
                       change_reason=change_reason)
    db.add(rev)
    db.flush()
    for a in db.execute(select(Attachment).where(Attachment.object_type == "item_revision",
                                                 Attachment.object_id == base.id)).scalars().all():
        db.add(Attachment(object_type="item_revision", object_id=rev.id, file_object_id=a.file_object_id,
                          filename=a.filename, doc_kind=a.doc_kind, description=a.description,
                          uploaded_by=actor.user_id))
    db.flush()
    audit.record(db, actor, "create", "item_revision", rev.id, _label(item, rev),
                 after={"supersedes": base.revision_label, **{f: getattr(rev, f) for f in CONTENT_FIELDS}},
                 reason=change_reason)
    return rev


def discard(db: Session, actor: Actor, item_id: uuid.UUID, rev_id: uuid.UUID, reason: str) -> None:
    item = _get_item(db, item_id)
    rev = _get_rev(db, item, rev_id)
    if rev.status != "Draft":
        raise Conflict("Only Draft revisions can be discarded")
    rev.status = "Discarded"
    db.flush()
    signatures.transition(db, actor, "item_revision", rev.id, "Draft", "Discarded", reason, label=_label(item, rev))


# ---------------- queries ----------------

def stock_summary(db: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, float]]:
    """on_hand: all; available: allocatable (Available lots, non-quarantine locations, not expired)."""
    from app.services.inventory import available_filter

    out: dict[uuid.UUID, dict[str, float]] = {i: {"on_hand": 0.0, "reserved": 0.0, "available": 0.0} for i in item_ids}
    if not item_ids:
        return out
    for iid, oh, rs in db.execute(
        select(InventoryLot.item_id, func.coalesce(func.sum(LotBalance.qty_on_hand), 0),
               func.coalesce(func.sum(LotBalance.qty_reserved), 0))
        .join(LotBalance, LotBalance.lot_id == InventoryLot.id)
        .where(InventoryLot.item_id.in_(item_ids)).group_by(InventoryLot.item_id)
    ):
        out[iid]["on_hand"] = float(oh)
        out[iid]["reserved"] = float(rs)
    q = available_filter(
        select(InventoryLot.item_id, func.coalesce(func.sum(LotBalance.qty_on_hand - LotBalance.qty_reserved), 0))
        .join(LotBalance, LotBalance.lot_id == InventoryLot.id)
    ).where(InventoryLot.item_id.in_(item_ids)).group_by(InventoryLot.item_id)
    for iid, av in db.execute(q):
        out[iid]["available"] = float(av)
    return out


def list_items(db: Session, q: str | None, status: str | None, limit: int, offset: int) -> dict[str, Any]:
    latest = (select(ItemRevision.item_id, func.max(ItemRevision.created_at).label("mx"))
              .group_by(ItemRevision.item_id).subquery())
    base = (select(Item, ItemRevision).join(latest, latest.c.item_id == Item.id)
            .join(ItemRevision, (ItemRevision.item_id == Item.id) & (ItemRevision.created_at == latest.c.mx)))
    if q:
        like = f"%{q}%"
        mpn_items = select(AmlEntry.item_id).join(ManufacturerPart, ManufacturerPart.id == AmlEntry.manufacturer_part_id)\
            .where(ManufacturerPart.mpn.ilike(like))
        base = base.where(or_(Item.part_number.ilike(like), ItemRevision.description.ilike(like),
                              ItemRevision.value.ilike(like), ItemRevision.package.ilike(like),
                              Item.id.in_(mpn_items)))
    if status:
        base = base.where(ItemRevision.status == status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.order_by(Item.part_number).limit(limit).offset(offset)).all()
    stock = stock_summary(db, [i.id for i, _r in rows])
    rel = {r.id: r for r in db.execute(select(ItemRevision).where(
        ItemRevision.id.in_([i.current_released_revision_id for i, _r in rows if i.current_released_revision_id]))).scalars()}
    items = []
    for i, r in rows:
        cr = rel.get(i.current_released_revision_id) if i.current_released_revision_id else None
        items.append({
            "id": str(i.id), "part_number": i.part_number, "item_class": i.item_class, "uom": i.uom,
            "description": r.description, "value": r.value, "package": r.package, "category": r.category,
            "latest_revision": r.revision_label, "latest_status": r.status,
            "released_revision": cr.revision_label if cr else None, "released_status": cr.status if cr else None,
            "min_stock": float(i.min_stock), **stock[i.id],
        })
    return {"total": total, "items": items}


def _rev_dict(db: Session, item: Item, r: ItemRevision, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    atts = db.execute(select(Attachment, FileObject).join(FileObject, FileObject.id == Attachment.file_object_id)
                      .where(Attachment.object_type == "item_revision", Attachment.object_id == r.id)
                      .order_by(Attachment.uploaded_at)).all()
    return {
        "id": str(r.id), "revision_label": r.revision_label, "status": r.status, "row_version": r.row_version,
        "review_cycle": r.review_cycle, "content_hash": r.content_hash,
        **{f: getattr(r, f) for f in CONTENT_FIELDS},
        "created_at": r.created_at, "created_by": names.get(r.created_by), "created_by_id": str(r.created_by),
        "modified_at": r.modified_at, "modified_by": names.get(r.modified_by),
        "submitted_at": r.submitted_at, "approved_at": r.approved_at, "released_at": r.released_at,
        "is_current_released": item.current_released_revision_id == r.id,
        "signatures": signatures.list_for(db, "item_revision", r.id),
        "transitions": signatures.transitions_for(db, "item_revision", r.id),
        "attachments": [{"id": str(a.id), "filename": a.filename, "doc_kind": a.doc_kind, "description": a.description,
                         "sha256": f.sha256, "size_bytes": f.size_bytes, "mime_type": f.mime_type,
                         "uploaded_at": a.uploaded_at, "uploaded_by": names.get(a.uploaded_by)} for a, f in atts],
    }


def item_detail(db: Session, item_id: uuid.UUID) -> dict[str, Any]:
    item = _get_item(db, item_id)
    names = dict(db.execute(select(User.id, User.full_name)).all())
    revs = db.execute(select(ItemRevision).where(ItemRevision.item_id == item.id)
                      .order_by(ItemRevision.created_at.desc())).scalars().all()
    aml = db.execute(select(AmlEntry, ManufacturerPart, Manufacturer)
                     .join(ManufacturerPart, ManufacturerPart.id == AmlEntry.manufacturer_part_id)
                     .join(Manufacturer, Manufacturer.id == ManufacturerPart.manufacturer_id)
                     .where(AmlEntry.item_id == item.id).order_by(AmlEntry.preferred.desc(), Manufacturer.name)).all()
    return {
        "id": str(item.id), "part_number": item.part_number, "item_class": item.item_class, "uom": item.uom,
        "min_stock": float(item.min_stock), "created_at": item.created_at, "created_by": names.get(item.created_by),
        "current_released_revision_id": str(item.current_released_revision_id) if item.current_released_revision_id else None,
        "revisions": [_rev_dict(db, item, r, names) for r in revs],
        "aml": [{"id": str(a.id), "status": a.status, "preferred": a.preferred, "notes": a.notes,
                 "qualification_status": a.qualification_status, "manufacturer": m.name, "mpn": mp.mpn,
                 "manufacturer_part_id": str(mp.id), "lifecycle": mp.lifecycle, "datasheet_url": mp.datasheet_url,
                 "sources": [{"id": str(ds.id), "distributor": ds.distributor_name,
                              "source_part_number": ds.source_part_number, "source_url": ds.source_url,
                              "preferred": ds.preferred}
                             for ds in db.execute(select(DistributorSource).where(DistributorSource.manufacturer_part_id == mp.id)
                                                .order_by(DistributorSource.preferred.desc(), DistributorSource.distributor_name)).scalars().all()],
                 "approved_at": a.approved_at, "approved_by": names.get(a.approved_by) if a.approved_by else None,
                 "signatures": signatures.list_for(db, "aml_entry", a.id)} for a, mp, m in aml],
        "stock": stock_summary(db, [item.id])[item.id],
    }


# ---------------- AML ----------------

def get_or_create_mpn(db: Session, actor: Actor, manufacturer: str, mpn: str, **attrs: Any) -> ManufacturerPart:
    manufacturer, mpn = manufacturer.strip(), mpn.strip()
    if not manufacturer or not mpn:
        raise DomainError("Manufacturer and MPN are required", "validation")
    m = db.execute(select(Manufacturer).where(Manufacturer.name == manufacturer)).scalar_one_or_none()
    if m is None:
        m = Manufacturer(name=manufacturer)
        db.add(m)
        db.flush()
        audit.record(db, actor, "create", "manufacturer", m.id, manufacturer, after={"name": manufacturer})
    mp = db.execute(select(ManufacturerPart).where(ManufacturerPart.manufacturer_id == m.id,
                                                   ManufacturerPart.mpn == mpn)).scalar_one_or_none()
    if mp is None:
        mp = ManufacturerPart(manufacturer_id=m.id, mpn=mpn, **{k: v for k, v in attrs.items() if v is not None})
        db.add(mp)
        db.flush()
        audit.record(db, actor, "create", "manufacturer_part", mp.id, f"{manufacturer} {mpn}",
                     after={"manufacturer": manufacturer, "mpn": mpn, **attrs})
    return mp


def add_aml(db: Session, actor: Actor, item_id: uuid.UUID, manufacturer: str, mpn: str, preferred: bool,
            notes: str | None, distributor: str | None = None, source_part_number: str | None = None,
            source_url: str | None = None, **attrs: Any) -> AmlEntry:
    item = _get_item(db, item_id)
    mp = get_or_create_mpn(db, actor, manufacturer, mpn, **attrs)
    if db.execute(select(AmlEntry).where(AmlEntry.item_id == item.id,
                                         AmlEntry.manufacturer_part_id == mp.id)).scalar_one_or_none():
        raise Conflict("This manufacturer part is already on the AML for this item")
    e = AmlEntry(item_id=item.id, manufacturer_part_id=mp.id, status="Proposed", preferred=preferred, notes=notes,
                 created_by=actor.user_id)
    db.add(e)
    db.flush()
    if distributor and distributor.strip():
        ds = DistributorSource(manufacturer_part_id=mp.id, distributor_name=distributor.strip(),
                               source_part_number=(source_part_number or "").strip() or None,
                               source_url=(source_url or "").strip() or None, preferred=True, created_by=actor.user_id)
        db.add(ds); db.flush()
        audit.record(db, actor, "create", "distributor_source", ds.id,
                     f"{distributor.strip()} {source_part_number or ''}".strip(),
                     after={"manufacturer_part_id": str(mp.id), "distributor": distributor.strip(),
                            "source_part_number": ds.source_part_number, "source_url": ds.source_url, "preferred": True})
    audit.record(db, actor, "create", "aml_entry", e.id, f"{item.part_number} ← {manufacturer} {mpn}",
                 after={"status": "Proposed", "preferred": preferred, "notes": notes})
    return e


def add_distributor_source(db: Session, actor: Actor, item_id: uuid.UUID, aml_id: uuid.UUID, distributor: str,
                           source_part_number: str | None, source_url: str | None, preferred: bool = False) -> None:
    item = _get_item(db, item_id)
    e = db.execute(select(AmlEntry).where(AmlEntry.id == aml_id, AmlEntry.item_id == item.id)).scalar_one_or_none()
    if e is None:
        raise NotFound("AML entry")
    name = distributor.strip()
    if not name:
        raise DomainError("Distributor / source is required", "validation")
    if preferred:
        for existing in db.execute(select(DistributorSource).where(DistributorSource.manufacturer_part_id == e.manufacturer_part_id)).scalars():
            existing.preferred = False
    ds = DistributorSource(manufacturer_part_id=e.manufacturer_part_id, distributor_name=name,
                           source_part_number=(source_part_number or "").strip() or None,
                           source_url=(source_url or "").strip() or None, preferred=preferred, created_by=actor.user_id)
    db.add(ds); db.flush()
    audit.record(db, actor, "create", "distributor_source", ds.id, f"{name} {source_part_number or ''}".strip(),
                 after={"manufacturer_part_id": str(e.manufacturer_part_id), "distributor": name,
                        "source_part_number": ds.source_part_number, "source_url": ds.source_url, "preferred": preferred})


def sign_aml(db: Session, actor: Actor, item_id: uuid.UUID, aml_id: uuid.UUID, meaning: str, password: str,
             comment: str | None) -> None:
    item = _get_item(db, item_id)
    e = db.execute(select(AmlEntry).where(AmlEntry.id == aml_id, AmlEntry.item_id == item.id)
                   .with_for_update()).scalar_one_or_none()
    if e is None:
        raise NotFound("AML entry")
    if meaning == "AML Approved" and e.status != "Proposed":
        raise Conflict("Only Proposed entries can be approved")
    if meaning == "AML Disqualified" and e.status == "Disqualified":
        raise Conflict("Already disqualified")
    if meaning not in ("AML Approved", "AML Disqualified"):
        raise DomainError("Invalid meaning for AML entry")
    if (get_settings().enforce_separation_of_duties and meaning == "AML Approved"
            and e.created_by == actor.user_id):
        raise Forbidden("Separation of duties: the proposer cannot approve the AML entry", "sod")
    sig = signatures.sign(db, actor, object_type="aml_entry", object_id=e.id, meaning=meaning, password=password,
                          comment=comment, label=item.part_number)
    frm = e.status
    e.status = "Approved" if meaning == "AML Approved" else "Disqualified"
    if e.status == "Approved":
        e.approved_at = func.clock_timestamp()
        e.approved_by = actor.user_id
    db.flush()
    signatures.transition(db, actor, "aml_entry", e.id, frm, e.status, comment, sig.id, item.part_number)
