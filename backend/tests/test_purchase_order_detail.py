import uuid
from decimal import Decimal

from conftest import PW


def test_purchase_order_detail_lines_approval_and_receipts(clients, released_part, locs):
    buyer, qa = clients['buyer'], clients['qa']
    code = 'PO' + uuid.uuid4().hex[:8].upper()
    supplier = buyer.post('/api/suppliers', json={'code': code, 'name': 'Detail supplier ' + code}).json()
    assert qa.post(f"/api/suppliers/{supplier['id']}/approve", json={'password': PW}).status_code == 200
    line = {'item_id': released_part['id'],
            'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id'],
            'supplier_part_number': 'SUP-123', 'qty_ordered': 4, 'unit_cost': '1.25'}
    response = buyer.post('/api/purchase-orders', json={'supplier_id': supplier['id'], 'currency': 'GBP',
        'expected_date': '2027-01-15', 'notes': 'Keep original packaging',
        'lines': [line, {**line, 'qty_ordered': 2, 'unit_cost': '0.125'}]})
    assert response.status_code == 200, response.text
    po = response.json()
    url = f"/api/purchase-orders/{po['id']}"
    detail = clients['ro'].get(url)
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data['supplier_code'] == code
    assert data['notes'] == 'Keep original packaging'
    assert data['expected_date'] == '2027-01-15'
    assert data['created_by'] and data['created_at']
    assert Decimal(data['total']) == Decimal('5.25')
    assert data['lines'][0]['part_number'] == released_part['part_number']
    assert data['lines'][0]['supplier_part_number'] == 'SUP-123'
    assert data['lines'][0]['mpn'] and data['lines'][0]['manufacturer']
    assert Decimal(data['lines'][0]['qty_outstanding']) == 4
    assert data['signatures'] == [] and data['receipts'] == []
    assert clients['ro'].post(url + '/approve', json={'password': PW}).status_code == 403
    response = buyer.post(url + '/approve', json={'password': PW, 'comment': 'Reviewed order'})
    assert response.status_code == 200, response.text
    assert response.json()['signatures'][0]['meaning'] == 'Purchase Order Approved'
    response = buyer.post(url + '/receive', json={'location_id': locs['a']['id'],
        'lines': [{'po_line_id': po['lines'][0]['id'], 'qty': 1}]})
    assert response.status_code == 200, response.text
    data = clients['ro'].get(url).json()
    assert data['status'] == 'Partially Received'
    assert Decimal(data['lines'][0]['qty_received']) == 1
    assert Decimal(data['lines'][0]['qty_outstanding']) == 3
    assert data['receipts'][0]['lot_id'] == response.json()['lot_ids'][0]
    assert data['receipts'][0]['po_line_id'] == po['lines'][0]['id']
    assert clients['ro'].get(f'/api/purchase-orders/{uuid.uuid4()}').status_code == 404


def test_draft_editing_audit_stale_revisions_and_approval_lock(clients, released_part):
    buyer, qa = clients['buyer'], clients['qa']
    code = 'ED' + uuid.uuid4().hex[:8].upper()
    supplier = buyer.post('/api/suppliers', json={'code': code, 'name': code}).json()
    qa.post(f"/api/suppliers/{supplier['id']}/approve", json={'password': PW})
    line = {'item_id': released_part['id'], 'qty_ordered': 2, 'unit_cost': '1.25',
            'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id'], 'supplier_part_number': 'ORIGINAL'}
    po = buyer.post('/api/purchase-orders', json={'supplier_id': supplier['id'], 'currency': 'GBP', 'lines': [line]}).json()
    url = f"/api/purchase-orders/{po['id']}"
    edit = {'supplier_id': supplier['id'], 'revision': 1, 'currency': 'USD', 'expected_date': '2027-03-01', 'notes': 'Updated order',
            'reason': 'Add parts for the build', 'lines': [dict(line, id=po['lines'][0]['id'], qty_ordered=3), dict(line, qty_ordered=4)]}
    assert clients['ro'].put(url, json=edit).status_code == 403
    assert buyer.put(url, json=dict(edit, reason='   ')).status_code == 400
    assert buyer.put(url, json=dict(edit, lines=[])).status_code == 422
    assert buyer.put(url, json=dict(edit, lines=[dict(line, qty_ordered=-1)])).status_code == 422
    assert buyer.put(url, json=dict(edit, lines=[dict(line, qty_ordered='0.5')])).status_code == 400
    assert buyer.put(url, json=dict(edit, lines=[dict(line, id=str(uuid.uuid4()))])).status_code == 400
    assert buyer.put(url, json=dict(edit, lines=[edit['lines'][0], edit['lines'][0]])).status_code == 400
    assert buyer.get(url).json()['revision'] == 1
    r = buyer.put(url, json=edit)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved['revision'] == 2 and len(saved['lines']) == 2
    assert saved['lines'][0]['id'] == po['lines'][0]['id']
    assert Decimal(saved['total']) == Decimal('8.75')
    assert buyer.put(url, json=edit).status_code == 409
    assert buyer.post(url+'/approve', json={'password': PW, 'revision': 1}).status_code == 409
    # Removing the first line keeps the second line's identity and renumbers it safely.
    edit['revision'] = 2
    edit['lines'] = [dict(line, id=saved['lines'][1]['id'], supplier_part_number='CHANGED')]
    r = buyer.put(url, json=edit)
    assert r.status_code == 200, r.text
    assert r.json()['lines'][0]['line_no'] == 1
    assert r.json()['lines'][0]['id'] == saved['lines'][1]['id']
    events = qa.get('/api/audit', params={'entity_id': po['id'], 'action': 'modify'}).json()['items']
    assert len(events) == 2 and events[0]['reason'] == edit['reason']
    assert len(events[0]['before']['lines']) == 2 and len(events[0]['after']['lines']) == 1
    approved = buyer.post(url+'/approve', json={'password': PW, 'revision': 3})
    assert approved.status_code == 200, approved.text
    edit['revision'] = 3
    assert buyer.put(url, json=edit).status_code == 409
    assert buyer.get(url).json()['lines'][0]['supplier_part_number'] == 'CHANGED'
    assert qa.get('/api/audit/verify').json()['ok']


def test_po_receipt_partial_duplicate_and_complete(clients, released_part, locs):
    buyer, qa = clients['buyer'], clients['qa']
    code = 'RC' + uuid.uuid4().hex[:8].upper()
    supplier = buyer.post('/api/suppliers', json={'code': code, 'name': code}).json()
    qa.post(f"/api/suppliers/{supplier['id']}/approve", json={'password': PW})
    # Legacy orders can omit the manufacturer; the actual approved source is recorded on receipt.
    po = buyer.post('/api/purchase-orders', json={'supplier_id': supplier['id'], 'currency': 'GBP',
        'lines': [{'item_id': released_part['id'], 'qty_ordered': 10, 'unit_cost': 1, 'supplier_part_number': 'SUP-RC'}]}).json()
    url = f"/api/purchase-orders/{po['id']}"
    buyer.post(url+'/approve', json={'password': PW})
    payload = {'location_id': locs['a']['id'], 'lines': [{'po_line_id': po['lines'][0]['id'], 'qty': 4,
        'expected_qty_received': 0, 'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id'],
        'supplier_lot': 'DELIVERY-1'}]}
    assert clients['prod'].post(url+'/receive', json=payload).status_code == 403
    r = buyer.post(url+'/receive', json=payload)
    assert r.status_code == 200, r.text
    lot = buyer.get('/api/lots/'+r.json()['lot_ids'][0]).json()
    assert lot['purchase_order_ref'] == po['po_number']
    assert lot['purchase_order_id'] == po['id']
    assert lot['supplier_part_number'] == 'SUP-RC' and lot['supplier_name'] == code
    assert lot['supplier_lot'] == 'DELIVERY-1' and lot['status'] == 'Pending Inspection'
    assert buyer.post(url+'/receive', json=payload).status_code == 409
    after = buyer.get(url).json()
    assert after['status'] == 'Partially Received' and len(after['receipts']) == 1
    assert Decimal(after['lines'][0]['qty_outstanding']) == 6
    payload['lines'][0].update(expected_qty_received=4, qty=7)
    assert buyer.post(url+'/receive', json=payload).status_code == 409
    payload['lines'][0]['qty'] = 6
    assert buyer.post(url+'/receive', json=payload).status_code == 200
    after = buyer.get(url).json()
    assert after['status'] == 'Received' and len(after['receipts']) == 2
    assert Decimal(after['lines'][0]['qty_outstanding']) == 0
    assert buyer.post(url+'/receive', json=payload).status_code == 409
    assert clients['admin'].get('/api/inventory/verify').json()['ok']


def test_concurrent_same_po_receipt_is_not_duplicated(app, users, clients, released_part, locs):
    from concurrent.futures import ThreadPoolExecutor
    from conftest import Client
    buyer, qa = clients['buyer'], clients['qa']
    code = 'CC' + uuid.uuid4().hex[:8].upper()
    supplier = buyer.post('/api/suppliers', json={'code': code, 'name': code}).json()
    qa.post(f"/api/suppliers/{supplier['id']}/approve", json={'password': PW})
    po = buyer.post('/api/purchase-orders', json={'supplier_id': supplier['id'], 'currency': 'GBP',
        'lines': [{'item_id': released_part['id'], 'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id'],
                   'qty_ordered': 10, 'unit_cost': 1}]}).json()
    url = f"/api/purchase-orders/{po['id']}"
    buyer.post(url+'/approve', json={'password': PW})
    payload = {'location_id': locs['a']['id'], 'lines': [{'po_line_id': po['lines'][0]['id'], 'qty': 4, 'expected_qty_received': 0}]}
    mismatched = {'location_id': locs['a']['id'], 'lines': [dict(payload['lines'][0], manufacturer_part_id=str(uuid.uuid4()))]}
    assert buyer.post(url+'/receive', json=mismatched).status_code == 409
    browsers = [Client(app, users['buyer']), Client(app, users['buyer'])]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c: c.post(url+'/receive', json=payload).status_code, browsers))
        assert sorted(results) == [200, 409]
        detail = buyer.get(url).json()
        assert len(detail['receipts']) == 1
        assert Decimal(detail['lines'][0]['qty_received']) == 4
    finally:
        for browser in browsers:
            browser.c.__exit__(None, None, None)


def test_part_selector_returns_mpn_and_supports_mpn_search(clients, released_part):
    mpn = released_part['aml'][0]['mpn']
    response = clients['buyer'].get('/api/items', params={'q': mpn})
    assert response.status_code == 200, response.text
    part = next(p for p in response.json()['items'] if p['id'] == released_part['id'])
    assert mpn in part['mpns']
    assert part['part_number'] == released_part['part_number']
    assert 'description' in part
