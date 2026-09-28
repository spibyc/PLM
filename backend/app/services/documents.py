"""Controlled-document register supporting ISO 13485-style document and record controls.

This module supports, but by itself does not establish, conformity. Procedures, retention periods,
roles and validation must be defined by the organisation for its intended use and regulations.
"""
import datetime as dt
import hashlib
import uuid
import calendar
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.context import Actor
from app.core.errors import Conflict, DomainError, NotFound
from app.models import ControlledDocument, DocumentRevision, FileObject, User
from app.services import audit, files, signatures

ALLOWED_STATUS = {"Draft", "In Review", "Released", "Superseded", "Obsolete"}

def _add_months(d:dt.date, months:int)->dt.date:
    y=d.year+(d.month-1+months)//12; m=(d.month-1+months)%12+1
    return dt.date(y,m,min(d.day,calendar.monthrange(y,m)[1]))

def _doc(db, did):
    x=db.get(ControlledDocument,did)
    if not x: raise NotFound("Document")
    return x

def _rev(db, rid):
    x=db.get(DocumentRevision,rid)
    if not x: raise NotFound("Document revision")
    return x

def _payload(d:ControlledDocument,r:DocumentRevision,fo:FileObject)->str:
    # Release hash binds controlled metadata and exact immutable file bytes.
    raw="|".join([d.document_number,d.title,d.document_type,r.revision,r.change_summary,fo.sha256])
    return hashlib.sha256(raw.encode()).hexdigest()

def create_document(db:Session,actor:Actor,**v):
    if db.execute(select(ControlledDocument).where(func.lower(ControlledDocument.document_number)==v['document_number'].lower())).scalar_one_or_none():
        raise Conflict("Document number already exists")
    rev=v.pop('revision'); change=v.pop('change_summary')
    d=ControlledDocument(**v,created_by=actor.user_id); db.add(d); db.flush()
    r=DocumentRevision(document_id=d.id,revision=rev,status="Draft",change_summary=change,prepared_by=actor.user_id)
    db.add(r); db.flush(); audit.record(db,actor,"create","controlled_document",d.id,d.document_number,after={"revision":rev,"title":d.title,"status":"Draft"}); return d,r

def new_revision(db:Session,actor:Actor,did:uuid.UUID,revision:str,change_summary:str):
    d=_doc(db,did)
    if not d.active: raise Conflict("Obsolete documents cannot receive new revisions")
    if db.execute(select(DocumentRevision).where(DocumentRevision.document_id==did,DocumentRevision.status.in_(["Draft","In Review"]))).scalar_one_or_none():
        raise Conflict("This document already has an open draft/review revision")
    if db.execute(select(DocumentRevision).where(DocumentRevision.document_id==did,DocumentRevision.revision==revision)).scalar_one_or_none(): raise Conflict("Revision label already exists")
    r=DocumentRevision(document_id=did,revision=revision,status="Draft",change_summary=change_summary,prepared_by=actor.user_id); db.add(r); db.flush(); audit.record(db,actor,"new_revision","controlled_document",did,d.document_number,after={"revision":revision,"change_summary":change_summary}); return r

def upload_revision(db:Session,actor:Actor,did:uuid.UUID,rid:uuid.UUID,stream,filename:str):
    d=_doc(db,did); r=_rev(db,rid)
    if r.document_id!=did: raise NotFound("Document revision")
    if r.status!="Draft": raise Conflict("Only Draft revisions can receive a controlled file")
    fo,safe=files.store(db,actor,stream,filename)
    before={"filename":r.filename,"file_sha256":db.get(FileObject,r.file_object_id).sha256 if r.file_object_id else None}
    r.file_object_id=fo.id; r.filename=safe; r.content_hash=None
    audit.record(db,actor,"document_file_set","document_revision",r.id,f"{d.document_number} Rev {r.revision}",before=before,after={"filename":safe,"file_sha256":fo.sha256}); return r

def submit_review(db,actor,did,rid):
    d=_doc(db,did); r=_rev(db,rid)
    if r.document_id!=did: raise NotFound("Document revision")
    if r.status!="Draft": raise Conflict("Only Draft revisions can be submitted")
    if not r.file_object_id: raise Conflict("Upload the controlled file before review")
    r.status="In Review"; signatures.transition(db,actor,"document_revision",r.id,"Draft","In Review",label=f"{d.document_number} Rev {r.revision}"); return r

def release(db:Session,actor:Actor,did,rid,password,comment,effective_date=None):
    d=_doc(db,did); r=_rev(db,rid)
    if r.document_id!=did: raise NotFound("Document revision")
    if r.status not in {"Draft","In Review"}: raise Conflict("Only Draft/In Review revisions can be released")
    if not r.file_object_id: raise Conflict("A controlled file is required before release")
    fo=db.get(FileObject,r.file_object_id); h=_payload(d,r,fo)
    sig=signatures.sign(db,actor,object_type="document_revision",object_id=r.id,meaning="Document Released",password=password,comment=comment,content_hash=h,label=f"{d.document_number} Rev {r.revision}")
    old_status=r.status
    today=effective_date or dt.date.today(); r.status="Released"; r.content_hash=h; r.effective_date=today; r.released_at=func.clock_timestamp(); r.released_by=actor.user_id
    if d.review_interval_months: r.review_due_date=_add_months(today,d.review_interval_months)
    r.retention_until=_add_months(today,12*max(2,d.retention_years))
    olds=db.execute(select(DocumentRevision).where(DocumentRevision.document_id==did,DocumentRevision.id!=rid,DocumentRevision.status=="Released")).scalars().all()
    for old in olds:
        old.status="Superseded"; signatures.transition(db,actor,"document_revision",old.id,"Released","Superseded",reason=f"Superseded by Rev {r.revision}",label=f"{d.document_number} Rev {old.revision}")
    signatures.transition(db,actor,"document_revision",r.id,old_status,"Released",signature_id=sig.id,label=f"{d.document_number} Rev {r.revision}")
    return r

def obsolete(db,actor,did,password,comment):
    d=_doc(db,did)
    if not comment or len(comment.strip())<3: raise DomainError("Reason is required","comment_required")
    current=db.execute(select(DocumentRevision).where(DocumentRevision.document_id==did,DocumentRevision.status=="Released").order_by(DocumentRevision.created_at.desc())).scalars().first()
    if not current: raise Conflict("No released revision to obsolete")
    sig=signatures.sign(db,actor,object_type="document_revision",object_id=current.id,meaning="Document Obsoleted",password=password,comment=comment,content_hash=current.content_hash,label=f"{d.document_number} Rev {current.revision}")
    current.status="Obsolete"; current.obsolete_at=func.clock_timestamp(); current.obsolete_by=actor.user_id; d.active=False
    signatures.transition(db,actor,"document_revision",current.id,"Released","Obsolete",reason=comment,signature_id=sig.id,label=f"{d.document_number} Rev {current.revision}")

def list_documents(db):
    docs=db.execute(select(ControlledDocument).order_by(ControlledDocument.document_number)).scalars().all(); return [detail(db,d.id,compact=True) for d in docs]

def detail(db,did,compact=False):
    d=_doc(db,did); revs=db.execute(select(DocumentRevision).where(DocumentRevision.document_id==did).order_by(DocumentRevision.created_at.desc())).scalars().all()
    rr=[]
    for r in revs:
        fo=db.get(FileObject,r.file_object_id) if r.file_object_id else None
        preparer=db.get(User,r.prepared_by)
        rr.append({"id":str(r.id),"revision":r.revision,"status":r.status,"change_summary":r.change_summary,"filename":r.filename,"file_sha256":fo.sha256 if fo else None,"content_hash":r.content_hash,"release_candidate_hash":_payload(d,r,fo) if fo and r.status in {"Draft","In Review"} else r.content_hash,"effective_date":r.effective_date,"review_due_date":r.review_due_date,"retention_until":r.retention_until,"created_at":r.created_at,"prepared_by":preparer.full_name if preparer else None,"released_at":r.released_at,"signatures":signatures.list_for(db,"document_revision",r.id) if not compact else []})
    current=next((x for x in rr if x['status']=="Released"),None) or (rr[0] if rr else None)
    return {"id":str(d.id),"document_number":d.document_number,"title":d.title,"document_type":d.document_type,"owner_department":d.owner_department,"source":d.source,"external_reference":d.external_reference,"product_or_project":d.product_or_project,"retention_years":d.retention_years,"review_interval_months":d.review_interval_months,"active":d.active,"current":current,"revisions":rr if not compact else []}
