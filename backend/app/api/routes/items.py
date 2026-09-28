import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require
from app.context import Actor
from app.db import get_db
from app.models import ItemRevision
from app.models.items import ITEM_CLASSES, MFR_LIFECYCLE, UOMS
from app.core.errors import NotFound
from app.services import files, items

router = APIRouter(prefix="/api/items", tags=["items"])


class Content(BaseModel):
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    component_type: str | None = Field(default=None, max_length=100)
    value: str | None = Field(default=None, max_length=100)
    package: str | None = Field(default=None, max_length=100)
    rohs_status: str | None = Field(default=None, max_length=32)
    reach_status: str | None = Field(default=None, max_length=32)
    notes: str | None = None
    change_reason: str | None = None


class ItemCreate(Content):
    item_class: str = "component"
    uom: str = "pcs"
    min_stock: Decimal = Decimal(0)
    description: str = Field(min_length=1, max_length=500)


class RevisionEdit(Content):
    row_version: int


class SignIn(BaseModel):
    meaning: str
    password: str
    comment: str | None = None
    content_hash: str | None = None


class NewRevisionIn(BaseModel):
    change_reason: str = Field(min_length=3)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3)


class AdminRevisionEdit(RevisionEdit):
    reason: str = Field(min_length=3)


class PlanningIn(BaseModel):
    min_stock: Decimal = Field(ge=0)
    reason: str = Field(min_length=3)


class AmlIn(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=200)
    mpn: str = Field(min_length=1, max_length=100)
    preferred: bool = False
    notes: str | None = None
    lifecycle: str | None = None
    datasheet_url: str | None = None
    rohs_status: str | None = None
    reach_status: str | None = None
    country_of_origin: str | None = None
    distributor: str | None = Field(default=None, max_length=200)
    source_part_number: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)


class DistributorSourceIn(BaseModel):
    distributor: str = Field(min_length=1, max_length=200)
    source_part_number: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=500)
    preferred: bool = False


class AmlSignIn(BaseModel):
    meaning: str
    password: str
    comment: str | None = None


@router.get("/meta")
def meta(actor: Actor = Depends(require("item:read"))) -> dict:
    return {"item_classes": ITEM_CLASSES, "uoms": UOMS, "doc_kinds": files.DOC_KINDS,
            "mfr_lifecycles": MFR_LIFECYCLE, "allowed_extensions": sorted(files.ALLOWED)}


@router.get("")
def list_items(q: str | None = None, status: str | None = None, limit: int = Query(50, le=500),
               offset: int = 0, actor: Actor = Depends(require("item:read")), db: Session = Depends(get_db)) -> dict:
    return items.list_items(db, q, status, limit, offset)


@router.post("")
def create(body: ItemCreate, actor: Actor = Depends(require("item:write")), db: Session = Depends(get_db)) -> dict:
    from app.core.errors import DomainError

    if body.item_class not in ITEM_CLASSES or body.uom not in UOMS:
        raise DomainError("Invalid item class or unit of measure", "validation")
    item = items.create_item(db, actor, body.item_class, body.uom, body.model_dump(), float(body.min_stock))
    db.commit()
    return items.item_detail(db, item.id)


@router.get("/{item_id}")
def detail(item_id: uuid.UUID, actor: Actor = Depends(require("item:read")), db: Session = Depends(get_db)) -> dict:
    return items.item_detail(db, item_id)


@router.put("/{item_id}/planning")
def planning(item_id: uuid.UUID, body: PlanningIn, actor: Actor = Depends(require("item:write")),
             db: Session = Depends(get_db)) -> dict:
    items.update_planning(db, actor, item_id, float(body.min_stock), body.reason)
    db.commit()
    return items.item_detail(db, item_id)


@router.patch("/{item_id}/revisions/{rev_id}")
def edit(item_id: uuid.UUID, rev_id: uuid.UUID, body: RevisionEdit, actor: Actor = Depends(require("item:write")),
         db: Session = Depends(get_db)) -> dict:
    items.edit_draft(db, actor, item_id, rev_id, body.row_version, body.model_dump(exclude_unset=True, exclude={"row_version"}))
    db.commit()
    return items.item_detail(db, item_id)


@router.patch("/{item_id}/revisions/{rev_id}/admin-override")
def admin_edit(item_id: uuid.UUID, rev_id: uuid.UUID, body: AdminRevisionEdit,
               actor: Actor = Depends(require("admin:override")), db: Session = Depends(get_db)) -> dict:
    changes = body.model_dump(exclude_unset=True, exclude={"row_version", "reason"})
    items.admin_edit_revision(db, actor, item_id, rev_id, body.row_version, changes, body.reason)
    db.commit()
    return items.item_detail(db, item_id)


@router.delete("/{item_id}")
def admin_delete(item_id: uuid.UUID, body: ReasonIn, actor: Actor = Depends(require("admin:override")),
                 db: Session = Depends(get_db)) -> dict:
    try:
        label = items.admin_delete_item(db, actor, item_id, body.reason)
        db.commit()
        return {"deleted": True, "part_number": label}
    except Exception:
        db.rollback()
        raise


@router.post("/{item_id}/revisions/{rev_id}/submit")
def submit(item_id: uuid.UUID, rev_id: uuid.UUID, actor: Actor = Depends(require("item:write")),
           db: Session = Depends(get_db)) -> dict:
    items.submit(db, actor, item_id, rev_id)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/revisions/{rev_id}/sign")
def sign(item_id: uuid.UUID, rev_id: uuid.UUID, body: SignIn, actor: Actor = Depends(require("item:read")),
         db: Session = Depends(get_db)) -> dict:
    items.sign(db, actor, item_id, rev_id, body.meaning, body.password, body.comment, body.content_hash)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/revisions/{rev_id}/discard")
def discard(item_id: uuid.UUID, rev_id: uuid.UUID, body: ReasonIn, actor: Actor = Depends(require("item:write")),
            db: Session = Depends(get_db)) -> dict:
    items.discard(db, actor, item_id, rev_id, body.reason)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/revisions")
def new_revision(item_id: uuid.UUID, body: NewRevisionIn, actor: Actor = Depends(require("item:write")),
                 db: Session = Depends(get_db)) -> dict:
    items.new_revision(db, actor, item_id, body.change_reason)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/revisions/{rev_id}/attachments")
def upload(item_id: uuid.UUID, rev_id: uuid.UUID, file: UploadFile = File(...), doc_kind: str = Form(...),
           description: str | None = Form(None), actor: Actor = Depends(require("files:upload")),
           db: Session = Depends(get_db)) -> dict:
    rev = db.get(ItemRevision, rev_id)
    if rev is None or rev.item_id != item_id:
        raise NotFound("Revision")
    from app.core.errors import Conflict

    if rev.status != "Draft":
        raise Conflict("Files can only be added to a Draft revision. Create a new revision.", "locked")
    files.attach(db, actor, "item_revision", rev.id, file.file, file.filename or "", doc_kind, description,
                 f"rev {rev.revision_label}")
    rev.row_version += 1
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/aml")
def add_aml(item_id: uuid.UUID, body: AmlIn, actor: Actor = Depends(require("aml:write")),
            db: Session = Depends(get_db)) -> dict:
    attrs = body.model_dump(exclude={"manufacturer", "mpn", "preferred", "notes", "distributor", "source_part_number", "source_url"})
    if attrs.get("lifecycle") is None:
        attrs["lifecycle"] = "Unknown"
    items.add_aml(db, actor, item_id, body.manufacturer, body.mpn, body.preferred, body.notes,
                  body.distributor, body.source_part_number, body.source_url, **attrs)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/aml/{aml_id}/sources")
def add_distributor_source(item_id: uuid.UUID, aml_id: uuid.UUID, body: DistributorSourceIn,
                           actor: Actor = Depends(require("aml:write")), db: Session = Depends(get_db)) -> dict:
    items.add_distributor_source(db, actor, item_id, aml_id, body.distributor, body.source_part_number,
                                 body.source_url, body.preferred)
    db.commit()
    return items.item_detail(db, item_id)


@router.post("/{item_id}/aml/{aml_id}/sign")
def sign_aml(item_id: uuid.UUID, aml_id: uuid.UUID, body: AmlSignIn, actor: Actor = Depends(require("item:read")),
             db: Session = Depends(get_db)) -> dict:
    items.sign_aml(db, actor, item_id, aml_id, body.meaning, body.password, body.comment)
    db.commit()
    return items.item_detail(db, item_id)
