"""Retirement preserves quantities, reservations, ledger history and access controls."""
import uuid

import pytest
from sqlalchemy import select

from app.core.errors import Conflict
from app.db import new_session
from app.models import Location
from app.services import inventory


def make_location(clients, **extra):
    r = clients['admin'].post('/api/locations', json={
        'kind': 'site', 'segment': 'T' + uuid.uuid4().hex[:10], 'name': 'Retirement test', **extra})
    assert r.status_code == 200, r.text
    return r.json()


def unallocated(clients):
    return next(l for l in clients['admin'].get('/api/locations?include_system=true').json()
                if l['system_key'] == 'unallocated')


def retire(clients, loc, reason='Storage reorganised'):
    return clients['admin'].post(f"/api/locations/{loc['id']}/retire", json={'reason': reason})


def test_empty_retirement_permissions_reason_and_history(clients):
    loc = make_location(clients)
    url = f"/api/locations/{loc['id']}/retire"
    for role in ('ro', 'prod', 'eng', 'qa'):
        assert clients[role].post(url, json={'reason': 'No longer used'}).status_code == 403
    for body in ({}, {'reason': ''}, {'reason': '   '}):
        assert clients['admin'].post(url, json=body).status_code in (400, 422)
    assert clients['admin'].get(f"/api/locations/{loc['id']}").json()['is_active']
    r = retire(clients, loc)
    assert r.status_code == 200, r.text
    assert not r.json()['is_active'] and r.json()['retired_at']
    assert loc['id'] not in {l['id'] for l in clients['admin'].get('/api/locations').json()}
    assert clients['ro'].get(f"/api/locations/{loc['id']}").status_code == 200
    assert clients['ro'].get(f"/api/locations/by-code/{loc['code']}").json()['id'] == loc['id']
    assert retire(clients, loc).status_code == 409
    assert clients['admin'].patch(f"/api/locations/{loc['id']}", json={
        'is_active': True, 'reason': 'Reactivate'}).status_code == 409
    audit = clients['admin'].get('/api/audit', params={'entity_id': loc['id'], 'action': 'retire'}).json()['items']
    assert len(audit) == 1
    assert audit[0]['reason'] == 'Storage reorganised'
    assert audit[0]['before']['is_active'] is True
    assert audit[0]['after']['stock_moved'] == []
    assert audit[0]['actor'] == clients['admin'].username
    assert audit[0]['occurred_at']


def test_system_and_children_protected(clients):
    system = unallocated(clients)
    assert retire(clients, system).status_code == 409
    assert system['id'] not in {l['id'] for l in clients['admin'].get('/api/locations').json()}
    assert clients['admin'].patch(f"/api/locations/{system['id']}", json={
        'is_active': False, 'reason': 'Disable'}).status_code == 409
    assert clients['admin'].post('/api/locations', json={
        'parent_id': system['id'], 'kind': 'room', 'segment': 'A', 'name': 'Child'}).status_code == 409
    parent = make_location(clients)
    child = make_location(clients, parent_id=parent['id'], kind='room')
    assert 'child locations' in retire(clients, parent).json()['detail']
    assert retire(clients, child).status_code == 200
    # Retain historical hierarchy too; no recursive deletion.
    assert retire(clients, parent).status_code == 409


def test_stock_reservations_reconciliation_and_reallocation(clients, available_lot, locs):
    loc, dst = make_location(clients), unallocated(clients)
    prod, admin = clients['prod'], clients['admin']
    lid = available_lot['id']
    base = f'/api/lots/{lid}'
    assert prod.post(base + '/transfer', json={
        'from_location_id': locs['a']['id'], 'to_location_id': loc['id'], 'qty': 100}).status_code == 200
    assert prod.post(base + '/reserve', json={
        'location_id': loc['id'], 'qty': 35, 'reference': 'BUILD-RESERVED'}).status_code == 200
    assert retire(clients, loc).status_code == 200
    lot = prod.get(base).json()
    assert lot['qty_on_hand'] == 100
    assert lot['balances'][0]['location_id'] == dst['id']
    assert lot['balances'][0]['qty_reserved'] == 35
    moves = [t for t in lot['transactions'] if (t['comment'] or '').startswith('Location retirement:')]
    assert len(moves) == 2
    assert sum(t['d_on_hand'] for t in moves) == 0
    assert sum(t['d_reserved'] for t in moves) == 0
    assert {t['location'] for t in moves} == {loc['code'], 'UNALLOCATED'}
    assert len({t['correlation_id'] for t in moves}) == 1
    history = admin.get(f"/api/locations/{loc['id']}").json()
    assert not history['stock'] and history['recent_movements']
    assert admin.get('/api/inventory/verify').json()['ok']
    ev = admin.get('/api/audit', params={'action': 'retire', 'entity_id': loc['id']}).json()['items'][0]
    assert ev['after']['stock_moved'][0]['qty_reserved'] == '35.000000'
    assert prod.post(base + '/issue', json={
        'location_id': dst['id'], 'qty': 1, 'reference': 'BUILD'}).status_code == 409
    assert prod.post(base + '/reserve', json={
        'location_id': dst['id'], 'qty': 1, 'reference': 'BUILD'}).status_code == 409
    assert prod.post(base + '/adjust', json={
        'location_id': loc['id'], 'delta': 1, 'reason': 'Try retired'}).status_code == 400
    # Moving reserved units requires an explicit reserved quantity, preserving old transfer defaults.
    assert prod.post(base + '/transfer', json={
        'from_location_id': dst['id'], 'to_location_id': locs['b']['id'], 'qty': 100}).status_code == 409
    r = prod.post(base + '/transfer', json={
        'from_location_id': dst['id'], 'to_location_id': locs['b']['id'], 'qty': 100, 'qty_reserved': 35})
    assert r.status_code == 200, r.text
    assert r.json()['balances'][0]['qty_reserved'] == 35
    assert r.json()['qty_on_hand'] == 100
    assert admin.get('/api/inventory/verify').json()['ok']


@pytest.mark.parametrize('quarantined', [False, True])
def test_pending_or_quarantined_lots_can_be_retired(clients, released_part, quarantined):
    loc = make_location(clients, is_quarantine=quarantined)
    prod = clients['prod']
    r = prod.post('/api/lots', json={'item_id': released_part['id'], 'qty': 7, 'location_id': loc['id'],
        'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id']})
    assert r.status_code == 200, r.text
    lot = r.json()
    if quarantined:
        assert prod.post(f"/api/lots/{lot['id']}/quarantine", json={'reason': 'NCR test'}).status_code == 200
    assert retire(clients, loc).status_code == 200
    after = prod.get(f"/api/lots/{lot['id']}").json()
    assert after['qty_on_hand'] == 7
    assert after['status'] == ('Quarantined' if quarantined else 'Pending Inspection')
    assert after['balances'][0]['location_code'] == 'UNALLOCATED'


def test_retirement_rolls_back_on_posting_failure(clients, available_lot, locs, monkeypatch):
    loc = make_location(clients)
    lid = available_lot['id']
    clients['prod'].post(f'/api/lots/{lid}/transfer', json={
        'from_location_id': locs['a']['id'], 'to_location_id': loc['id'], 'qty': 20})
    original = inventory._post
    def fail_incoming(db, actor, **kw):
        if kw['txn_type'] == 'TRANSFER_IN':
            raise Conflict('Simulated posting failure')
        return original(db, actor, **kw)
    monkeypatch.setattr(inventory, '_post', fail_incoming)
    assert retire(clients, loc).status_code == 409
    after = clients['admin'].get(f"/api/locations/{loc['id']}").json()
    assert after['is_active'] and after['stock'][0]['qty_on_hand'] == 20
    assert not clients['admin'].get('/api/audit', params={'action': 'retire', 'entity_id': loc['id']}).json()['items']
    assert clients['admin'].get('/api/inventory/verify').json()['ok']


def test_busy_location_returns_conflict(clients):
    loc = make_location(clients)
    with new_session() as db:
        db.execute(select(Location).where(Location.id == uuid.UUID(loc['id'])).with_for_update(read=True))
        assert retire(clients, loc).json()['code'] == 'location_busy'
    assert retire(clients, loc).status_code == 200


def test_busy_lot_returns_conflict_and_receipt_into_retired_is_blocked(clients, available_lot, locs):
    from app.models import InventoryLot
    loc = make_location(clients)
    lid = available_lot['id']
    prod = clients['prod']
    assert prod.post(f'/api/lots/{lid}/transfer', json={
        'from_location_id': locs['a']['id'], 'to_location_id': loc['id'], 'qty': 10}).status_code == 200
    with new_session() as db:
        db.execute(select(InventoryLot).where(InventoryLot.id == uuid.UUID(lid)).with_for_update())
        assert retire(clients, loc).json()['code'] == 'location_busy'
    assert retire(clients, loc).status_code == 200
    assert prod.post(f'/api/lots/{lid}/transfer', json={
        'from_location_id': locs['a']['id'], 'to_location_id': loc['id'], 'qty': 1}).status_code == 400
    assert clients['admin'].post('/api/locations', json={
        'parent_id': loc['id'], 'kind': 'room', 'segment': 'NEW', 'name': 'New child'}).status_code == 400
    with new_session() as db:
        assert inventory.verify_balances(db)['ok']


def test_multi_lot_retirement_and_reserved_quantity_validation(clients, available_lot, released_part, locs):
    loc = make_location(clients)
    prod = clients['prod']
    first_id = available_lot['id']
    second = prod.post('/api/lots', json={
        'item_id': released_part['id'], 'qty': 12, 'location_id': loc['id'],
        'manufacturer_part_id': released_part['aml'][0]['manufacturer_part_id']}).json()
    assert prod.post(f'/api/lots/{first_id}/transfer', json={
        'from_location_id': locs['a']['id'], 'to_location_id': loc['id'], 'qty': 10}).status_code == 200
    for reserved in (-1, 11, 0.5, 1):
        response = prod.post(f'/api/lots/{first_id}/transfer', json={
            'from_location_id': loc['id'], 'to_location_id': locs['b']['id'], 'qty': 10,
            'qty_reserved': reserved})
        assert response.status_code in (400, 409, 422)
    assert retire(clients, loc).status_code == 200
    system = unallocated(clients)
    stock = clients['admin'].get(f"/api/locations/{system['id']}").json()['stock']
    moved = {s['lot_id']: s['qty_on_hand'] for s in stock}
    assert moved[first_id] == 10 and moved[second['id']] == 12
    assert clients['admin'].get('/api/inventory/verify').json()['ok']
    assert clients['admin'].get('/api/audit/verify').json()['ok']
