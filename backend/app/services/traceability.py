import csv, hashlib, io, uuid
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.context import Actor
from app.core.errors import Conflict, DomainError, NotFound
from app.models import *
from app.services import audit, inventory, signatures
from app.services.audit import canonical
from app.services.numbering import next_number

def _dict(o, fields): return {f:getattr(o,f) for f in fields}
def supplier_dict(x): return _dict(x,['id','code','name','status','risk_class','website','notes','created_at','created_by','approved_at','approved_by'])
def list_suppliers(db):
    return [supplier_dict(x) for x in db.execute(select(Supplier).order_by(Supplier.code)).scalars()]
def supplier_detail(db,sid):
    x=db.get(Supplier,sid)
    if not x: raise NotFound('Supplier')
    return supplier_dict(x)
def update_supplier(db,actor,sid,code,name,risk_class='Medium',website=None,notes=None):
    x=db.get(Supplier,sid)
    if not x: raise NotFound('Supplier')
    if x.status!='Draft': raise Conflict('Only Draft suppliers can be edited; suspend an approved supplier or create a new qualification record')
    before=supplier_dict(x); x.code=code.strip().upper(); x.name=name.strip(); x.risk_class=risk_class; x.website=website; x.notes=notes; db.flush()
    audit.record(db,actor,'update','supplier',x.id,x.code,before=before,after=supplier_dict(x)); return x
def set_supplier_status(db,actor,sid,status,reason):
    x=db.get(Supplier,sid)
    if not x: raise NotFound('Supplier')
    allowed={'Approved':{'Suspended','Inactive'},'Suspended':{'Approved','Inactive'}}
    if status not in allowed.get(x.status,set()): raise Conflict(f'Supplier cannot transition from {x.status} to {status}')
    if not reason or len(reason.strip())<3: raise DomainError('Reason is required','validation')
    old=x.status; x.status=status; signatures.transition(db,actor,'supplier',x.id,old,status,reason,None,x.code); audit.record(db,actor,'status','supplier',x.id,x.code,before={'status':old},after={'status':status,'reason':reason}); return x
def create_supplier(db, actor, code,name,risk_class='Medium',website=None,notes=None):
    x=Supplier(code=code.strip().upper(),name=name.strip(),risk_class=risk_class,website=website,notes=notes,created_by=actor.user_id); db.add(x); db.flush(); audit.record(db,actor,'create','supplier',x.id,x.code,after={'name':x.name,'risk_class':risk_class}); return x
def approve_supplier(db,actor,sid,password,comment=None):
    x=db.get(Supplier,sid); 
    if not x: raise NotFound('Supplier')
    if x.status!='Draft': raise Conflict('Only Draft suppliers can be approved')
    sig=signatures.sign(db,actor,object_type='supplier',object_id=x.id,meaning='Supplier Approved',password=password,comment=comment,label=x.code,review_cycle=signatures.next_event_cycle(db,'supplier',x.id)); old=x.status; x.status='Approved'; x.approved_by=actor.user_id; x.approved_at=func.clock_timestamp(); signatures.transition(db,actor,'supplier',x.id,old,x.status,comment,sig.id,x.code)

def create_po(db,actor,supplier_id,currency,expected_date,notes,lines):
    s=db.get(Supplier,supplier_id)
    if not s or s.status!='Approved': raise Conflict('Purchase orders require an Approved supplier')
    po=PurchaseOrder(po_number=next_number(db,'PO'),supplier_id=s.id,currency=currency.upper(),expected_date=expected_date,notes=notes,created_by=actor.user_id); db.add(po); db.flush()
    for i,l in enumerate(lines,1): db.add(PurchaseOrderLine(po_id=po.id,line_no=i,item_id=l['item_id'],manufacturer_part_id=l.get('manufacturer_part_id'),supplier_part_number=l.get('supplier_part_number'),qty_ordered=Decimal(str(l['qty_ordered'])),unit_cost=Decimal(str(l['unit_cost']))))
    audit.record(db,actor,'create','purchase_order',po.id,po.po_number,after={'supplier':s.code,'currency':po.currency,'lines':len(lines)}); return po
def update_po(db, actor, pid, supplier_id, revision, currency, expected_date, notes, reason, lines):
    po = db.execute(select(PurchaseOrder).where(PurchaseOrder.id == pid).with_for_update()).scalar_one_or_none()
    if not po:
        raise NotFound('Purchase order')
    if po.status != 'Draft':
        raise Conflict('Only Draft purchase orders can be edited')
    if po.revision != revision:
        raise Conflict('This purchase order has changed. Reload it before editing.', 'stale_revision')
    if len(reason.strip()) < 3:
        raise DomainError('A reason for the change is required', 'validation')
    if not lines:
        raise DomainError('At least one order line is required', 'validation')
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise DomainError('Currency must be a three-letter code', 'validation')
    supplier = db.get(Supplier, supplier_id)
    if not supplier or supplier.status != 'Approved':
        raise Conflict('Purchase orders require an Approved supplier')
    existing = {line.id: line for line in db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == pid)).scalars()}
    seen = set()
    for line in lines:
        lid = line.get('id')
        if lid and (lid not in existing or lid in seen):
            raise DomainError('Invalid or duplicate purchase order line', 'validation')
        if lid:
            seen.add(lid)
        item = db.get(Item, line['item_id'])
        if not item:
            raise NotFound('Part')
        qty, cost = Decimal(str(line['qty_ordered'])), Decimal(str(line['unit_cost']))
        if not qty.is_finite() or not cost.is_finite() or qty <= 0 or cost < 0:
            raise DomainError('Quantity must be positive and unit cost cannot be negative', 'validation')
        if item.uom == 'pcs' and qty != qty.to_integral_value():
            raise DomainError('Quantities in pcs must be whole numbers', 'validation')
        if len(line.get('supplier_part_number') or '') > 100:
            raise DomainError('Supplier part number must be at most 100 characters', 'validation')
        mpid = line.get('manufacturer_part_id')
        if mpid and not db.execute(select(AmlEntry.id).where(AmlEntry.item_id == item.id,
                AmlEntry.manufacturer_part_id == mpid, AmlEntry.status == 'Approved')).first():
            raise DomainError('Manufacturer part must be an approved source for this part', 'validation')
    before = po_detail(db, pid)
    # Renumber draft lines in a separate flush to avoid the (po_id, line_no) unique constraint.
    for index, old in enumerate(existing.values(), 1):
        old.line_no = -index
    db.flush()
    for lid, old in existing.items():
        if lid not in seen:
            db.delete(old)
    for index, line in enumerate(lines, 1):
        row = existing.get(line.get('id'))
        if row is None:
            row = PurchaseOrderLine(po_id=pid, qty_received=0)
            db.add(row)
        row.line_no = index
        for field in ('item_id', 'manufacturer_part_id', 'supplier_part_number', 'qty_ordered', 'unit_cost'):
            setattr(row, field, line.get(field))
    po.supplier_id = supplier_id
    po.currency, po.expected_date, po.notes = currency.upper(), expected_date, notes
    po.revision += 1
    db.flush()
    audit.record(db, actor, 'modify', 'purchase_order', po.id, po.po_number,
                 before=before, after=po_detail(db, pid), reason=reason.strip())

def approve_po(db,actor,pid,password,comment=None,revision=None):
    po=db.execute(select(PurchaseOrder).where(PurchaseOrder.id==pid).with_for_update()).scalar_one_or_none()
    if not po: raise NotFound('Purchase order')
    if po.status!='Draft': raise Conflict('Only Draft purchase orders can be approved')
    if revision is not None and po.revision != revision: raise Conflict('This purchase order has changed. Reload it before approving.', 'stale_revision')
    sig=signatures.sign(db,actor,object_type='purchase_order',object_id=po.id,meaning='Purchase Order Approved',password=password,comment=comment,label=po.po_number,review_cycle=1,content_hash=po_hash(db,po.id)); old=po.status; po.status='Approved'; po.approved_by=actor.user_id; po.approved_at=func.clock_timestamp(); signatures.transition(db,actor,'purchase_order',po.id,old,po.status,comment,sig.id,po.po_number)
def po_hash(db, pid):
    po = db.get(PurchaseOrder, pid)
    lines = db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == pid)
                       .order_by(PurchaseOrderLine.line_no)).scalars().all()
    return hashlib.sha256(canonical({
        'po': po.po_number, 'supplier': po.supplier_id, 'currency': po.currency,
        'revision': po.revision, 'expected_date': po.expected_date, 'notes': po.notes,
        'lines': [{'line': x.line_no, 'item': x.item_id, 'manufacturer_part': x.manufacturer_part_id,
                   'supplier_part_number': x.supplier_part_number, 'qty': x.qty_ordered, 'cost': x.unit_cost}
                  for x in lines],
    }).encode()).hexdigest()
def po_detail(db, pid):
    po = db.get(PurchaseOrder, pid)
    if not po:
        raise NotFound('Purchase order')
    supplier = db.get(Supplier, po.supplier_id)
    creator = db.get(User, po.created_by)
    rows = db.execute(
        select(PurchaseOrderLine, Item, ItemRevision, ManufacturerPart, Manufacturer)
        .join(Item, Item.id == PurchaseOrderLine.item_id)
        .outerjoin(ItemRevision, ItemRevision.id == Item.current_released_revision_id)
        .outerjoin(ManufacturerPart, ManufacturerPart.id == PurchaseOrderLine.manufacturer_part_id)
        .outerjoin(Manufacturer, Manufacturer.id == ManufacturerPart.manufacturer_id)
        .where(PurchaseOrderLine.po_id == pid).order_by(PurchaseOrderLine.line_no)
    ).all()
    lines = [{
        'id': line.id, 'line_no': line.line_no, 'item_id': line.item_id,
        'part_number': item.part_number, 'description': rev.description if rev else None, 'uom': item.uom,
        'manufacturer_part_id': line.manufacturer_part_id, 'manufacturer': maker.name if maker else None,
        'mpn': mp.mpn if mp else None, 'supplier_part_number': line.supplier_part_number,
        'qty_ordered': line.qty_ordered, 'qty_received': line.qty_received,
        'qty_outstanding': line.qty_ordered - line.qty_received, 'unit_cost': line.unit_cost,
        'line_total': line.qty_ordered * line.unit_cost,
    } for line, item, rev, mp, maker in rows]
    receipts = db.execute(
        select(GoodsReceipt, GoodsReceiptLine, InventoryLot)
        .join(GoodsReceiptLine, GoodsReceiptLine.receipt_id == GoodsReceipt.id)
        .join(InventoryLot, InventoryLot.id == GoodsReceiptLine.lot_id)
        .where(GoodsReceipt.po_id == pid).order_by(GoodsReceipt.received_at, InventoryLot.lot_no)
    ).all()
    return {
        'id': po.id, 'po_number': po.po_number, 'supplier': supplier.name, 'supplier_id': supplier.id,
        'supplier_code': supplier.code, 'status': po.status, 'currency': po.currency,
        'revision': po.revision, 'expected_date': po.expected_date, 'notes': po.notes,
        'created_at': po.created_at, 'created_by': creator.full_name if creator else None,
        'approved_at': po.approved_at, 'lines': lines,
        'total': sum((line['line_total'] for line in lines), Decimal(0)),
        'signatures': signatures.list_for(db, 'purchase_order', po.id),
        'receipts': [{'receipt_id': receipt.id, 'receipt_no': receipt.receipt_no,
                      'received_at': receipt.received_at, 'po_line_id': line.po_line_id,
                      'lot_id': lot.id, 'lot_no': lot.lot_no, 'qty': line.qty}
                     for receipt, line, lot in receipts],
    }
def list_pos(db): return [po_detail(db,x.id) for x in db.execute(select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())).scalars()]
def receive_po(db,actor,pid,location_id,lines,notes=None):
    po=db.execute(select(PurchaseOrder).where(PurchaseOrder.id==pid).with_for_update()).scalar_one_or_none()
    if not po: raise NotFound('Purchase order')
    if po.status not in ('Approved','Ordered','Partially Received'): raise Conflict('PO is not receivable')
    rec=GoodsReceipt(receipt_no=next_number(db,'GRN'),po_id=po.id,received_by=actor.user_id,notes=notes); db.add(rec); db.flush()
    for r in lines:
        pl=db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.id==r['po_line_id'],PurchaseOrderLine.po_id==po.id).with_for_update()).scalar_one_or_none()
        if not pl: raise DomainError('PO line not found','validation')
        expected = r.get('expected_qty_received')
        if expected is not None and Decimal(pl.qty_received) != Decimal(str(expected)):
            raise Conflict('This PO line has already been received or changed. Refresh the order before receiving more.', 'receipt_changed')
        received_mpn = r.get('manufacturer_part_id') or pl.manufacturer_part_id
        if pl.manufacturer_part_id and received_mpn != pl.manufacturer_part_id:
            raise Conflict('Received manufacturer part does not match the purchase order')
        qty=Decimal(str(r['qty']));
        if qty <= 0:
            raise DomainError('Receipt quantity must be positive', 'validation')
        if Decimal(pl.qty_received)+qty>Decimal(pl.qty_ordered): raise Conflict('Receipt exceeds ordered quantity')
        lot=inventory.receive(db,actor,item_id=pl.item_id,qty=qty,location_id=location_id,manufacturer_part_id=received_mpn,supplier_name=db.get(Supplier,po.supplier_id).name,supplier_part_number=pl.supplier_part_number,purchase_order_ref=po.po_number,supplier_lot=r.get('supplier_lot'),manufacturer_lot=r.get('manufacturer_lot'),date_code=r.get('date_code'),expiry_date=r.get('expiry_date'),notes=r.get('notes'))
        pl.qty_received=Decimal(pl.qty_received)+qty; db.add(GoodsReceiptLine(receipt_id=rec.id,po_line_id=pl.id,lot_id=lot.id,qty=qty))
    all_lines=db.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id==po.id)).scalars().all(); old=po.status; po.status='Received' if all(Decimal(x.qty_received)>=Decimal(x.qty_ordered) for x in all_lines) else 'Partially Received'; signatures.transition(db,actor,'purchase_order',po.id,old,po.status,'Goods receipt',None,po.po_number); audit.record(db,actor,'receive','goods_receipt',rec.id,rec.receipt_no,after={'po':po.po_number}); return rec

def create_bom(db,actor,product_item_id,name,revision,change_reason,lines):
    item=db.get(Item,product_item_id)
    if not item: raise NotFound('Product item')
    b=Bom(bom_number=next_number(db,'BOM'),product_item_id=item.id,name=name,created_by=actor.user_id); db.add(b); db.flush(); br=BomRevision(bom_id=b.id,revision=revision,status='Draft',change_reason=change_reason,created_by=actor.user_id); db.add(br); db.flush(); _replace_bom_lines(db,br,lines); audit.record(db,actor,'create','bom_revision',br.id,f'{b.bom_number} Rev {revision}',after={'lines':len(lines)}); return br
def _replace_bom_lines(db,br,lines):
    if br.status not in ('Draft','Under Review'): raise Conflict('Released BOM revisions are immutable')
    for i,l in enumerate(lines,1): db.add(BomLine(bom_revision_id=br.id,line_no=i,item_id=l['item_id'],quantity=Decimal(str(l['quantity'])),references=l.get('references'),dnp=bool(l.get('dnp',False)),notes=l.get('notes')))
def bom_hash(db,rid):
    br=db.get(BomRevision,rid); b=db.get(Bom,br.bom_id); lines=db.execute(select(BomLine).where(BomLine.bom_revision_id==rid).order_by(BomLine.line_no)).scalars().all(); payload={'bom':b.bom_number,'revision':br.revision,'lines':[{'line':x.line_no,'item':str(x.item_id),'qty':str(x.quantity),'refs':x.references,'dnp':x.dnp} for x in lines]}; return hashlib.sha256(canonical(payload).encode()).hexdigest()
def release_bom(db,actor,rid,password,comment=None):
    br=db.get(BomRevision,rid)
    if not br: raise NotFound('BOM revision')
    if br.status not in ('Draft','Under Review'): raise Conflict('BOM revision is not releasable')
    h=bom_hash(db,rid); sig=signatures.sign(db,actor,object_type='bom_revision',object_id=br.id,meaning='BOM Released',password=password,comment=comment,label=str(rid),review_cycle=1,content_hash=h); old=br.status;br.status='Released';br.content_hash=h;br.released_by=actor.user_id;br.released_at=func.clock_timestamp();signatures.transition(db,actor,'bom_revision',br.id,old,br.status,comment,sig.id,str(rid))
def bom_detail(db,rid):
    br=db.get(BomRevision,rid)
    if not br: raise NotFound('BOM revision')
    b=db.get(Bom,br.bom_id); lines=db.execute(select(BomLine).where(BomLine.bom_revision_id==rid).order_by(BomLine.line_no)).scalars().all(); return {'id':br.id,'bom_id':b.id,'bom_number':b.bom_number,'name':b.name,'product_item_id':b.product_item_id,'revision':br.revision,'status':br.status,'content_hash':br.content_hash,'lines':[{'id':x.id,'line_no':x.line_no,'item_id':x.item_id,'quantity':x.quantity,'references':x.references,'dnp':x.dnp} for x in lines]}
def list_boms(db): return [bom_detail(db,x.id) for x in db.execute(select(BomRevision).order_by(BomRevision.created_at.desc())).scalars()]
def buildability(db,rid,units):
    units=Decimal(str(units)); br=bom_detail(db,rid); out=[]
    for l in br['lines']:
        if l['dnp']: continue
        required=Decimal(l['quantity'])*units
        q=select(func.coalesce(func.sum(LotBalance.qty_on_hand-LotBalance.qty_reserved),0)).select_from(LotBalance).join(InventoryLot,InventoryLot.id==LotBalance.lot_id).where(InventoryLot.item_id==l['item_id']); q=inventory.available_filter(q); avail=Decimal(db.execute(q).scalar_one()); out.append({**l,'required':required,'available':avail,'shortage':max(Decimal(0),required-avail),'buildable':avail>=required})
    return {'units':units,'buildable':all(x['buildable'] for x in out),'lines':out}
def bom_cost(db,rid,units=1):
    units=Decimal(str(units)); br=bom_detail(db,rid); total=Decimal(0); lines=[]
    for l in br['lines']:
        if l['dnp']: continue
        cost=db.execute(select(PurchaseOrderLine.unit_cost,PurchaseOrder.currency).join(PurchaseOrder,PurchaseOrder.id==PurchaseOrderLine.po_id).where(PurchaseOrderLine.item_id==l['item_id'],PurchaseOrder.status.in_(['Approved','Ordered','Partially Received','Received','Closed'])).order_by(PurchaseOrder.created_at.desc()).limit(1)).first(); c=Decimal(cost[0]) if cost else None; cur=cost[1] if cost else None; ext=c*Decimal(l['quantity'])*units if c is not None else None; lines.append({**l,'unit_cost':c,'currency':cur,'extended':ext}); total += ext or 0
    currencies={x['currency'] for x in lines if x['currency']}; return {'units':units,'currency':next(iter(currencies)) if len(currencies)==1 else None,'mixed_currency':len(currencies)>1,'total':None if len(currencies)>1 else total,'lines':lines}
def import_kicad_csv(db,text):
    rows=[]; rdr=csv.DictReader(io.StringIO(text));
    for n,r in enumerate(rdr,2):
        pn=(r.get('Internal Part Number') or r.get('Part Number') or r.get('part_number') or '').strip(); refs=(r.get('Reference') or r.get('References') or r.get('refs') or '').strip(); qty=r.get('Quantity') or r.get('Qty') or (len([x for x in refs.replace(' ','').split(',') if x]) if refs else 1); item=db.execute(select(Item).where(Item.part_number==pn)).scalar_one_or_none(); rows.append({'row':n,'part_number':pn,'item_id':str(item.id) if item else None,'quantity':str(qty),'references':refs,'valid':bool(item),'error':None if item else 'Unknown internal part number'})
    return {'rows':rows,'valid':all(x['valid'] for x in rows)}

def create_build(db,actor,rid,quantity,notes=None):
    br=db.get(BomRevision,rid)
    if not br or br.status!='Released': raise Conflict('Production builds require a Released BOM revision')
    b=ProductionBuild(build_number=next_number(db,'BUILD'),bom_revision_id=rid,quantity=quantity,created_by=actor.user_id,notes=notes); db.add(b);db.flush();audit.record(db,actor,'create','production_build',b.id,b.build_number,after={'bom_revision':str(rid),'quantity':quantity});return b
def issue_to_build(db,actor,bid,bom_line_id,lot_id,location_id,qty,comment=None):
    b=db.execute(select(ProductionBuild).where(ProductionBuild.id==bid).with_for_update()).scalar_one_or_none()
    if not b: raise NotFound('Build')
    if b.status not in ('Planned','In Progress'): raise Conflict('Material can only be issued to an open build')
    line=db.get(BomLine,bom_line_id); lot=db.get(InventoryLot,lot_id)
    if not line or line.bom_revision_id!=b.bom_revision_id: raise DomainError('BOM line is not part of this build BOM','validation')
    if not lot or lot.item_id!=line.item_id: raise Conflict('Lot item does not match the BOM line')
    txn=inventory.issue(db,actor,lot_id,location_id,qty,b.build_number,comment); bm=BuildMaterial(build_id=b.id,bom_line_id=line.id,lot_id=lot.id,location_id=location_id,quantity=Decimal(str(qty)),stock_txn_id=txn.id,issued_by=actor.user_id);db.add(bm); old=b.status;b.status='In Progress';
    if old!=b.status: signatures.transition(db,actor,'production_build',b.id,old,b.status,'Material issued',None,b.build_number)
    audit.record(db,actor,'consume','build_material',b.id,b.build_number,after={'lot':lot.lot_no,'qty':qty,'bom_line':line.line_no}); return bm
def complete_build(db,actor,bid):
    b=db.get(ProductionBuild,bid)
    if not b: raise NotFound('Build')
    if b.status!='In Progress': raise Conflict('Only In Progress builds can be completed')
    br=bom_detail(db,b.bom_revision_id); mats=db.execute(select(BuildMaterial).where(BuildMaterial.build_id==b.id)).scalars().all()
    for l in br['lines']:
        if l['dnp']: continue
        used=sum((Decimal(x.quantity) for x in mats if x.bom_line_id==l['id']),Decimal(0)); need=Decimal(l['quantity'])*b.quantity
        if used<need: raise Conflict(f'Build is short material on BOM line {l["line_no"]}: {used} / {need}')
    old=b.status;b.status='Completed';signatures.transition(db,actor,'production_build',b.id,old,b.status,'Material requirements satisfied',None,b.build_number)
def release_build(db,actor,bid,password,comment=None):
    b=db.get(ProductionBuild,bid)
    if not b or b.status!='Completed': raise Conflict('Only Completed builds can be released')
    h=hashlib.sha256(canonical(genealogy_build(db,bid)).encode()).hexdigest();sig=signatures.sign(db,actor,object_type='production_build',object_id=b.id,meaning='Build Released',password=password,comment=comment,label=b.build_number,review_cycle=1,content_hash=h);old=b.status;b.status='Released';b.released_by=actor.user_id;b.released_at=func.clock_timestamp();signatures.transition(db,actor,'production_build',b.id,old,b.status,comment,sig.id,b.build_number)
def create_serials(db,actor,bid,serials):
    b=db.get(ProductionBuild,bid)
    if not b or b.status not in ('Completed','Released'): raise Conflict('Serials can only be created for completed builds')
    existing=db.execute(select(func.count()).select_from(FinishedSerial).where(FinishedSerial.build_id==bid)).scalar_one()
    if existing+len(serials)>b.quantity: raise Conflict('Serial count exceeds build quantity')
    out=[]
    for sn in serials:
        x=FinishedSerial(serial_number=sn.strip().upper(),build_id=bid);db.add(x);out.append(x)
    db.flush();audit.record(db,actor,'create','finished_serial',bid,b.build_number,after={'serials':[x.serial_number for x in out]});return out
def release_serial(db,actor,sid,password,comment=None):
    x=db.get(FinishedSerial,sid)
    if not x: raise NotFound('Serial')
    b=db.get(ProductionBuild,x.build_id)
    if b.status!='Released': raise Conflict('Parent build must be Released')
    sig=signatures.sign(db,actor,object_type='finished_serial',object_id=x.id,meaning='Serial Released',password=password,comment=comment,label=x.serial_number,review_cycle=1,content_hash=hashlib.sha256(canonical(genealogy_serial(db,x.id)).encode()).hexdigest());x.status='Released';x.released_by=actor.user_id;x.released_at=func.clock_timestamp();audit.record(db,actor,'release','finished_serial',x.id,x.serial_number,after={'status':'Released','signature_id':str(sig.id)})
def genealogy_build(db,bid):
    b=db.get(ProductionBuild,bid)
    if not b: raise NotFound('Build')
    br=bom_detail(db,b.bom_revision_id); mats=db.execute(select(BuildMaterial).where(BuildMaterial.build_id==bid)).scalars().all(); return {'build_id':b.id,'build_number':b.build_number,'status':b.status,'quantity':b.quantity,'bom':{'number':br['bom_number'],'revision':br['revision'],'content_hash':br['content_hash']},'materials':[{'bom_line_id':m.bom_line_id,'lot_id':m.lot_id,'lot_no':db.get(InventoryLot,m.lot_id).lot_no,'quantity':m.quantity,'stock_txn_id':m.stock_txn_id} for m in mats],'serials':[{'id':x.id,'serial_number':x.serial_number,'status':x.status} for x in db.execute(select(FinishedSerial).where(FinishedSerial.build_id==bid)).scalars()]}
def genealogy_serial(db,sid):
    x=db.get(FinishedSerial,sid)
    if not x: raise NotFound('Serial')
    return {'serial_id':x.id,'serial_number':x.serial_number,'status':x.status,'build':genealogy_build(db,x.build_id)}
def where_used(db,lot_id):
    lot=db.get(InventoryLot,lot_id)
    if not lot: raise NotFound('Lot')
    bids=db.execute(select(BuildMaterial.build_id).where(BuildMaterial.lot_id==lot_id).distinct()).scalars().all(); return {'lot_id':lot.id,'lot_no':lot.lot_no,'builds':[genealogy_build(db,x) for x in bids]}
def list_builds(db): return [genealogy_build(db,x.id) for x in db.execute(select(ProductionBuild).order_by(ProductionBuild.created_at.desc())).scalars()]
