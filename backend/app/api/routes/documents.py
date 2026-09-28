import datetime as dt
import uuid
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import require
from app.context import Actor
from app.db import get_db
from app.models import DocumentRevision, FileObject
from app.services import documents as dsvc, files, audit
from app.core.errors import NotFound
router=APIRouter(prefix="/api/documents",tags=["documents"])

class DocumentIn(BaseModel):
    document_number:str=Field(min_length=2,max_length=64); title:str=Field(min_length=2,max_length=240)
    document_type:str=Field(min_length=2,max_length=64); owner_department:str=Field(min_length=2,max_length=100)
    source:str="Internal"; external_reference:str|None=None; product_or_project:str|None=None
    retention_years:int=Field(default=10,ge=2,le=100); review_interval_months:int|None=Field(default=24,ge=1,le=120)
    revision:str=Field(min_length=1,max_length=32); change_summary:str=Field(min_length=3)
class RevisionIn(BaseModel): revision:str=Field(min_length=1,max_length=32); change_summary:str=Field(min_length=3)
class Signed(BaseModel): password:str; comment:str|None=None; effective_date:dt.date|None=None

@router.get("")
def list_docs(actor:Actor=Depends(require("document:read")),db:Session=Depends(get_db)): return dsvc.list_documents(db)
@router.post("")
def create(body:DocumentIn,actor:Actor=Depends(require("document:write")),db:Session=Depends(get_db)):
    d,r=dsvc.create_document(db,actor,**body.model_dump()); db.commit(); return dsvc.detail(db,d.id)
@router.get("/{did}")
def get(did:uuid.UUID,actor:Actor=Depends(require("document:read")),db:Session=Depends(get_db)): return dsvc.detail(db,did)
@router.post("/{did}/revisions")
def new_revision(did:uuid.UUID,body:RevisionIn,actor:Actor=Depends(require("document:write")),db:Session=Depends(get_db)):
    dsvc.new_revision(db,actor,did,body.revision,body.change_summary); db.commit(); return dsvc.detail(db,did)
@router.post("/{did}/revisions/{rid}/file")
def upload(did:uuid.UUID,rid:uuid.UUID,file:UploadFile=File(...),actor:Actor=Depends(require("document:upload")),db:Session=Depends(get_db)):
    dsvc.upload_revision(db,actor,did,rid,file.file,file.filename or ""); db.commit(); return dsvc.detail(db,did)
@router.post("/{did}/revisions/{rid}/submit")
def submit(did:uuid.UUID,rid:uuid.UUID,actor:Actor=Depends(require("document:write")),db:Session=Depends(get_db)):
    dsvc.submit_review(db,actor,did,rid); db.commit(); return dsvc.detail(db,did)
@router.post("/{did}/revisions/{rid}/release")
def release(did:uuid.UUID,rid:uuid.UUID,body:Signed,actor:Actor=Depends(require("sign:document_released")),db:Session=Depends(get_db)):
    dsvc.release(db,actor,did,rid,body.password,body.comment,body.effective_date); db.commit(); return dsvc.detail(db,did)
@router.post("/{did}/obsolete")
def obsolete(did:uuid.UUID,body:Signed,actor:Actor=Depends(require("sign:document_obsolete")),db:Session=Depends(get_db)):
    dsvc.obsolete(db,actor,did,body.password,body.comment); db.commit(); return dsvc.detail(db,did)
@router.get("/{did}/revisions/{rid}/download")
def download(did:uuid.UUID,rid:uuid.UUID,actor:Actor=Depends(require("document:read")),db:Session=Depends(get_db)):
    r=db.get(DocumentRevision,rid)
    if not r or r.document_id!=did or not r.file_object_id: raise NotFound("Document file")
    fo=db.get(FileObject,r.file_object_id); path=files._root()/fo.storage_key
    if not path.exists(): raise NotFound("Stored file")
    audit.record(db,actor,"download","document_revision",r.id,r.filename,after={"sha256":fo.sha256}); db.commit()
    return FileResponse(path,media_type=fo.mime_type,filename=r.filename)
