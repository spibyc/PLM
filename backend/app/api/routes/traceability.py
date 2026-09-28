import datetime as dt, uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import require
from app.context import Actor
from app.db import get_db
from app.services import traceability as t
router=APIRouter(prefix='/api',tags=['traceability'])
class Signed(BaseModel): password:str; comment:str|None=None
class SupplierIn(BaseModel): code:str=Field(min_length=2,max_length=32); name:str=Field(min_length=2,max_length=200); risk_class:str='Medium'; website:str|None=None; notes:str|None=None
class SupplierStatusIn(BaseModel): status:str; reason:str=Field(min_length=3)
class POLine(BaseModel): item_id:uuid.UUID; manufacturer_part_id:uuid.UUID|None=None; supplier_part_number:str|None=None; qty_ordered:Decimal=Field(gt=0); unit_cost:Decimal=Field(ge=0)
class POIn(BaseModel): supplier_id:uuid.UUID; currency:str=Field(min_length=3,max_length=3); expected_date:dt.date|None=None; notes:str|None=None; lines:list[POLine]=Field(min_length=1)
class ReceiptLine(BaseModel): po_line_id:uuid.UUID; qty:Decimal=Field(gt=0); supplier_lot:str|None=None; manufacturer_lot:str|None=None; date_code:str|None=None; expiry_date:dt.date|None=None; notes:str|None=None
class ReceiptIn(BaseModel): location_id:uuid.UUID; lines:list[ReceiptLine]=Field(min_length=1); notes:str|None=None
class BomLineIn(BaseModel): item_id:uuid.UUID; quantity:Decimal=Field(gt=0); references:str|None=None; dnp:bool=False; notes:str|None=None
class BomIn(BaseModel): product_item_id:uuid.UUID; name:str; revision:str; change_reason:str=Field(min_length=3); lines:list[BomLineIn]=Field(min_length=1)
class BuildIn(BaseModel): bom_revision_id:uuid.UUID; quantity:int=Field(gt=0); notes:str|None=None
class IssueIn(BaseModel): bom_line_id:uuid.UUID; lot_id:uuid.UUID; location_id:uuid.UUID; qty:Decimal=Field(gt=0); comment:str|None=None
class SerialsIn(BaseModel): serials:list[str]=Field(min_length=1)
@router.get('/suppliers')
def suppliers(actor:Actor=Depends(require('supplier:read')),db:Session=Depends(get_db)): return t.list_suppliers(db)
@router.post('/suppliers')
def supplier(body:SupplierIn,actor:Actor=Depends(require('supplier:write')),db:Session=Depends(get_db)): x=t.create_supplier(db,actor,**body.model_dump());db.commit();return t.supplier_detail(db,x.id)
@router.get('/suppliers/{sid}')
def supplier_get(sid:uuid.UUID,actor:Actor=Depends(require('supplier:read')),db:Session=Depends(get_db)): return t.supplier_detail(db,sid)
@router.put('/suppliers/{sid}')
def supplier_update(sid:uuid.UUID,body:SupplierIn,actor:Actor=Depends(require('supplier:write')),db:Session=Depends(get_db)): x=t.update_supplier(db,actor,sid,**body.model_dump());db.commit();return t.supplier_detail(db,x.id)
@router.post('/suppliers/{sid}/status')
def supplier_status(sid:uuid.UUID,body:SupplierStatusIn,actor:Actor=Depends(require('supplier:write')),db:Session=Depends(get_db)): x=t.set_supplier_status(db,actor,sid,body.status,body.reason);db.commit();return t.supplier_detail(db,x.id)
@router.post('/suppliers/{sid}/approve')
def supplier_approve(sid:uuid.UUID,body:Signed,actor:Actor=Depends(require('sign:supplier_approved')),db:Session=Depends(get_db)): t.approve_supplier(db,actor,sid,body.password,body.comment);db.commit();return {'ok':True}
@router.get('/purchase-orders')
def pos(actor:Actor=Depends(require('po:read')),db:Session=Depends(get_db)): return t.list_pos(db)
@router.post('/purchase-orders')
def po(body:POIn,actor:Actor=Depends(require('po:write')),db:Session=Depends(get_db)): x=t.create_po(db,actor,body.supplier_id,body.currency,body.expected_date,body.notes,[x.model_dump() for x in body.lines]);db.commit();return t.po_detail(db,x.id)
@router.get('/purchase-orders/{pid}')
def po_get(pid:uuid.UUID,actor:Actor=Depends(require('po:read')),db:Session=Depends(get_db)): return t.po_detail(db,pid)
@router.post('/purchase-orders/{pid}/approve')
def po_approve(pid:uuid.UUID,body:Signed,actor:Actor=Depends(require('sign:po_approved')),db:Session=Depends(get_db)): t.approve_po(db,actor,pid,body.password,body.comment);db.commit();return t.po_detail(db,pid)
@router.post('/purchase-orders/{pid}/receive')
def po_receive(pid:uuid.UUID,body:ReceiptIn,actor:Actor=Depends(require('po:receive')),db:Session=Depends(get_db)): x=t.receive_po(db,actor,pid,body.location_id,[z.model_dump() for z in body.lines],body.notes); db.flush(); from app.models import GoodsReceiptLine; from sqlalchemy import select; lot_ids=[str(v) for v in db.execute(select(GoodsReceiptLine.lot_id).where(GoodsReceiptLine.receipt_id==x.id)).scalars().all()]; db.commit(); return {'receipt_id':x.id,'receipt_no':x.receipt_no,'lot_ids':lot_ids}
@router.get('/boms')
def boms(actor:Actor=Depends(require('bom:read')),db:Session=Depends(get_db)): return t.list_boms(db)
@router.post('/boms')
def bom(body:BomIn,actor:Actor=Depends(require('bom:write')),db:Session=Depends(get_db)): x=t.create_bom(db,actor,body.product_item_id,body.name,body.revision,body.change_reason,[z.model_dump() for z in body.lines]);db.commit();return t.bom_detail(db,x.id)
@router.get('/boms/{rid}')
def bom_get(rid:uuid.UUID,actor:Actor=Depends(require('bom:read')),db:Session=Depends(get_db)): return t.bom_detail(db,rid)
@router.post('/boms/{rid}/release')
def bom_release(rid:uuid.UUID,body:Signed,actor:Actor=Depends(require('sign:bom_released')),db:Session=Depends(get_db)): t.release_bom(db,actor,rid,body.password,body.comment);db.commit();return t.bom_detail(db,rid)
@router.get('/boms/{rid}/buildability')
def buildability(rid:uuid.UUID,units:int=1,actor:Actor=Depends(require('bom:read')),db:Session=Depends(get_db)): return t.buildability(db,rid,units)
@router.get('/boms/{rid}/cost')
def cost(rid:uuid.UUID,units:int=1,actor:Actor=Depends(require('bom:read')),db:Session=Depends(get_db)): return t.bom_cost(db,rid,units)
@router.post('/boms/import/kicad-preview')
async def kicad(file:UploadFile=File(...),actor:Actor=Depends(require('bom:write')),db:Session=Depends(get_db)): return t.import_kicad_csv(db,(await file.read()).decode('utf-8-sig'))
@router.get('/builds')
def builds(actor:Actor=Depends(require('build:read')),db:Session=Depends(get_db)): return t.list_builds(db)
@router.post('/builds')
def build(body:BuildIn,actor:Actor=Depends(require('build:write')),db:Session=Depends(get_db)): x=t.create_build(db,actor,body.bom_revision_id,body.quantity,body.notes);db.commit();return t.genealogy_build(db,x.id)
@router.post('/builds/{bid}/issue')
def issue(bid:uuid.UUID,body:IssueIn,actor:Actor=Depends(require('build:write')),db:Session=Depends(get_db)): t.issue_to_build(db,actor,bid,**body.model_dump());db.commit();return t.genealogy_build(db,bid)
@router.post('/builds/{bid}/complete')
def complete(bid:uuid.UUID,actor:Actor=Depends(require('build:write')),db:Session=Depends(get_db)): t.complete_build(db,actor,bid);db.commit();return t.genealogy_build(db,bid)
@router.post('/builds/{bid}/release')
def release(bid:uuid.UUID,body:Signed,actor:Actor=Depends(require('sign:build_released')),db:Session=Depends(get_db)): t.release_build(db,actor,bid,body.password,body.comment);db.commit();return t.genealogy_build(db,bid)
@router.post('/builds/{bid}/serials')
def serials(bid:uuid.UUID,body:SerialsIn,actor:Actor=Depends(require('build:write')),db:Session=Depends(get_db)): t.create_serials(db,actor,bid,body.serials);db.commit();return t.genealogy_build(db,bid)
@router.post('/serials/{sid}/release')
def serial_release(sid:uuid.UUID,body:Signed,actor:Actor=Depends(require('sign:build_released')),db:Session=Depends(get_db)): t.release_serial(db,actor,sid,body.password,body.comment);db.commit();return t.genealogy_serial(db,sid)
@router.get('/serials/{sid}/genealogy')
def serial_genealogy(sid:uuid.UUID,actor:Actor=Depends(require('build:read')),db:Session=Depends(get_db)): return t.genealogy_serial(db,sid)
@router.get('/lots/{lot_id}/where-used')
def where_used(lot_id:uuid.UUID,actor:Actor=Depends(require('build:read')),db:Session=Depends(get_db)): return t.where_used(db,lot_id)
