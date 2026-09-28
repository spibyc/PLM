"""0.2 procurement-to-production acceptance and negative tests through the public API."""
import uuid
from conftest import PW

def test_supplier_po_bom_build_genealogy(clients,released_part,locs):
    buyer,qa,eng,prod=clients['buyer'],clients['qa'],clients['eng'],clients['prod']
    code='S'+uuid.uuid4().hex[:7].upper()
    r=buyer.post('/api/suppliers',json={'code':code,'name':'OQ Supplier '+code,'risk_class':'Medium'}); assert r.status_code==200,r.text
    sid=next(x['id'] for x in r.json() if x['code']==code)
    assert qa.post(f'/api/suppliers/{sid}/approve',json={'password':PW,'comment':'OQ qualification'}).status_code==200
    r=buyer.post('/api/purchase-orders',json={'supplier_id':sid,'currency':'GBP','lines':[{'item_id':released_part['id'],'manufacturer_part_id':released_part['aml'][0]['manufacturer_part_id'],'qty_ordered':2,'unit_cost':'1.25'}]}); assert r.status_code==200,r.text
    po=r.json(); assert buyer.post(f"/api/purchase-orders/{po['id']}/approve",json={'password':PW}).status_code==200
    line=po['lines'][0]
    r=buyer.post(f"/api/purchase-orders/{po['id']}/receive",json={'location_id':locs['a']['id'],'lines':[{'po_line_id':line['id'],'qty':3}]}); assert r.status_code==409
    r=buyer.post(f"/api/purchase-orders/{po['id']}/receive",json={'location_id':locs['a']['id'],'lines':[{'po_line_id':line['id'],'qty':2,'supplier_lot':'OQ-LOT'}]}); assert r.status_code==200,r.text
    lot=prod.get('/api/lots/'+r.json()['lot_ids'][0]).json(); assert qa.post(f"/api/lots/{lot['id']}/inspect",json={'accept':True,'password':PW,'comment':'Accepted'}).status_code==200
    r=eng.post('/api/boms',json={'product_item_id':released_part['id'],'name':'OQ Assembly','revision':'A','change_reason':'Initial','lines':[{'item_id':released_part['id'],'quantity':1,'references':'R1'}]}); assert r.status_code==200,r.text
    bom=r.json(); r=prod.post('/api/builds',json={'bom_revision_id':bom['id'],'quantity':1}); assert r.status_code==409
    assert eng.post(f"/api/boms/{bom['id']}/release",json={'password':PW,'comment':'OQ release'}).status_code==200
    r=prod.post('/api/builds',json={'bom_revision_id':bom['id'],'quantity':1}); assert r.status_code==200,r.text
    build=r.json(); assert prod.post(f"/api/builds/{build['build_id']}/complete").status_code==409
    r=prod.post(f"/api/builds/{build['build_id']}/issue",json={'bom_line_id':bom['lines'][0]['id'],'lot_id':lot['id'],'location_id':locs['a']['id'],'qty':1}); assert r.status_code==200,r.text
    assert prod.post(f"/api/builds/{build['build_id']}/complete").status_code==200
    assert qa.post(f"/api/builds/{build['build_id']}/release",json={'password':PW,'comment':'Production record reviewed'}).status_code==200
    r=prod.post(f"/api/builds/{build['build_id']}/serials",json={'serials':['OQ-'+uuid.uuid4().hex[:8].upper()]}); assert r.status_code==200
    serial=r.json()['serials'][0]
    assert qa.post(f"/api/serials/{serial['id']}/release",json={'password':PW}).status_code==200
    g=qa.get(f"/api/serials/{serial['id']}/genealogy"); assert g.status_code==200 and g.json()['build']['materials'][0]['lot_no']==lot['lot_no']
    w=qa.get(f"/api/lots/{lot['id']}/where-used"); assert w.status_code==200 and w.json()['builds'][0]['build_number']==build['build_number']

def test_unauthorised_roles_cannot_approve_supplier(clients):
    assert clients['prod'].post('/api/suppliers/00000000-0000-0000-0000-000000000000/approve',json={'password':PW}).status_code==403
