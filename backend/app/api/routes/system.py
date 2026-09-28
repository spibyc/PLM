import datetime as dt
import uuid

import segno
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_actor, require
from app.context import Actor
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db import current_schema_revision, get_db
from app.models import AuditEvent, InventoryLot, Location
from app.services import audit, files, reporting
from app.version import APP_NAME, EXPECTED_SCHEMA_REVISION

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> Response:
    rev = current_schema_revision(db)
    ok = rev == EXPECTED_SCHEMA_REVISION
    import json

    return Response(json.dumps({"ready": ok, "schema": rev, "expected_schema": EXPECTED_SCHEMA_REVISION}),
                    status_code=200 if ok else 503, media_type="application/json")


@router.get("/version")
def version(db: Session = Depends(get_db)) -> dict:
    st = get_settings()
    return {"application": APP_NAME, "version": st.app_version, "commit": st.git_commit, "build_time": st.build_time,
            "schema_revision": current_schema_revision(db), "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
            "environment": st.environment}


@router.get("/dashboard")
def dashboard(actor: Actor = Depends(require("item:read")), db: Session = Depends(get_db)) -> dict:
    return reporting.dashboard(db)


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=100), actor: Actor = Depends(current_actor),
           db: Session = Depends(get_db)) -> list[dict]:
    res = reporting.search(db, q)
    allowed = {"Part": "item:read", "Lot": "inventory:read", "Location": "location:read"}
    return [r for r in res if actor.has(allowed[r["type"]])]


def _qr(url: str) -> Response:
    import io

    buf = io.BytesIO()
    # Standalone SVG document (with xmlns) so it renders in <img> tags and label printers.
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, xmldecl=False)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/qr/location/{loc_id}.svg")
def qr_location(loc_id: uuid.UUID, actor: Actor = Depends(require("location:read")), db: Session = Depends(get_db)) -> Response:
    loc = db.get(Location, loc_id)
    if loc is None:
        raise NotFound("Location")
    return _qr(f"{get_settings().public_base_url}/scan/location/{loc.code}")


@router.get("/qr/lot/{lot_id}.svg")
def qr_lot(lot_id: uuid.UUID, actor: Actor = Depends(require("inventory:read")), db: Session = Depends(get_db)) -> Response:
    lot = db.get(InventoryLot, lot_id)
    if lot is None:
        raise NotFound("Lot")
    return _qr(f"{get_settings().public_base_url}/scan/lot/{lot.lot_no}")


@router.get("/qr/item/{item_id}.svg")
def qr_item(item_id: uuid.UUID, actor: Actor = Depends(require("item:read"))) -> Response:
    return _qr(f"{get_settings().public_base_url}/parts/{item_id}")


# ---------------- files ----------------

@router.get("/files/{attachment_id}/download")
def download(attachment_id: uuid.UUID, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)) -> FileResponse:
    a, fo, path = files.open_attachment(db, actor, attachment_id)
    needed = "item:read" if a.object_type == "item_revision" else "inventory:read"
    if not actor.has(needed):
        from app.core.errors import Forbidden

        raise Forbidden()
    db.commit()
    return FileResponse(path, media_type=fo.mime_type, filename=a.filename,
                        headers={"X-Checksum-SHA256": fo.sha256, "X-Content-Type-Options": "nosniff"})


@router.post("/files/verify")
def verify_files(actor: Actor = Depends(require("files:verify")), db: Session = Depends(get_db)) -> dict:
    res = files.verify_integrity(db, actor)
    db.commit()
    return res


# ---------------- audit ----------------

@router.get("/audit")
def audit_list(entity_type: str | None = None, entity_id: str | None = None, actor_name: str | None = None,
               action: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
               limit: int = Query(100, le=1000), offset: int = 0, actor: Actor = Depends(require("audit:read")),
               db: Session = Depends(get_db)) -> dict:
    q = reporting.audit_query(entity_type, entity_id, actor_name, action, date_from, date_to)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(q.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)).scalars()
    return {"total": total, "items": [reporting.audit_dict(e) for e in rows]}


@router.get("/audit/entity/{entity_type}/{entity_id}")
def audit_entity(entity_type: str, entity_id: str, actor: Actor = Depends(require("item:read")),
                 db: Session = Depends(get_db)) -> list[dict]:
    """Record history for a record the user may view (item, revision, lot, location)."""
    allowed = {"item": "item:read", "item_revision": "item:read", "aml_entry": "item:read",
               "inventory_lot": "inventory:read", "location": "location:read"}
    if entity_type not in allowed or not actor.has(allowed[entity_type]):
        from app.core.errors import Forbidden

        raise Forbidden()
    rows = db.execute(select(AuditEvent).where(AuditEvent.entity_type == entity_type,
                                               AuditEvent.entity_id == entity_id).order_by(AuditEvent.id)).scalars()
    return [reporting.audit_dict(e) for e in rows]


@router.get("/audit/export.csv")
def audit_export(entity_type: str | None = None, entity_id: str | None = None, actor_name: str | None = None,
                 action: str | None = None, date_from: dt.date | None = None, date_to: dt.date | None = None,
                 actor: Actor = Depends(require("audit:read")), db: Session = Depends(get_db)) -> PlainTextResponse:
    q = reporting.audit_query(entity_type, entity_id, actor_name, action, date_from, date_to)
    rows = list(db.execute(q.order_by(AuditEvent.id).limit(200_000)).scalars())
    audit.record(db, actor, "export", "audit_event", None, "audit trail CSV",
                 after={"rows": len(rows), "filters": {"entity_type": entity_type, "entity_id": entity_id,
                                                       "actor": actor_name, "action": action,
                                                       "from": date_from, "to": date_to}})
    db.commit()
    st = get_settings()
    header = (f"# PLM audit trail export; generated_by={actor.username}; app_version={st.app_version}; "
              f"filters=entity_type:{entity_type or '*'},entity_id:{entity_id or '*'},actor:{actor_name or '*'},"
              f"action:{action or '*'},from:{date_from or '*'},to:{date_to or '*'}\n")
    return PlainTextResponse(header + reporting.audit_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit-trail.csv"})


@router.get("/audit/verify")
def audit_verify(actor: Actor = Depends(require("audit:read")), db: Session = Depends(get_db)) -> dict:
    res = audit.verify_chain(db)
    audit.record(db, actor, "audit_chain_verification", "audit_event", None, "audit chain",
                 after={"ok": res["ok"], "events_checked": res["events_checked"]})
    db.commit()
    return res
