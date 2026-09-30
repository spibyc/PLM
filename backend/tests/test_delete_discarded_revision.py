import uuid


def test_delete_discarded_revision_retains_audit(clients, released_part):
    admin, eng = clients['admin'], clients['eng']
    url = f"/api/items/{released_part['id']}"
    original = admin.get(url).json()
    response = eng.post(url + '/revisions', json={'change_reason': 'Test revision'})
    assert response.status_code == 200, response.text
    rev = response.json()['revisions'][0]
    target = url + '/revisions/' + rev['id']
    reason = {'reason': 'Remove discarded test revision'}
    assert admin.request('DELETE', target, json=reason).status_code == 409
    assert eng.post(target + '/discard', json={'reason': 'Test finished'}).status_code == 200
    assert eng.request('DELETE', target, json=reason).status_code == 403
    assert admin.request('DELETE', target, json={'reason': '   '}).status_code == 400
    response = admin.request('DELETE', target, json=reason)
    assert response.status_code == 200, response.text
    assert response.json()['revisions'] == original['revisions']
    history = admin.get(f"/api/audit/entity/item_revision/{rev['id']}").json()
    assert any(e['action'] == 'create' for e in history)
    assert any(e['action'] == 'admin_delete_discarded_revision' for e in history)
    assert any(e['action'] == 'admin_delete_discarded_revision' for e in admin.get(f"/api/audit/entity/item/{released_part['id']}").json())
    assert admin.get('/api/audit/verify').json()['ok'] is True
    assert admin.request('DELETE', target, json=reason).status_code == 404
    assert admin.request('DELETE', url + '/revisions/' + original['revisions'][0]['id'], json=reason).status_code == 409


def test_delete_last_or_wrong_part_revision_rejected(clients):
    admin = clients['admin']
    item = admin.post('/api/items', json={'description': 'Only revision'}).json()
    rev = item['revisions'][0]
    target = f"/api/items/{item['id']}/revisions/{rev['id']}"
    reason = {'reason': 'Discard test'}
    assert admin.post(target + '/discard', json=reason).status_code == 200
    assert admin.request('DELETE', target, json=reason).status_code == 409
    other = admin.post('/api/items', json={'description': 'Other part'}).json()
    assert admin.request('DELETE', f"/api/items/{other['id']}/revisions/{rev['id']}", json=reason).status_code == 404


def test_referenced_discarded_revision_cannot_be_deleted(clients, released_part, app_db):
    from sqlalchemy import text
    admin = clients['admin']
    url = f"/api/items/{released_part['id']}"
    discarded = admin.post(url + '/revisions', json={'change_reason': 'First test'}).json()['revisions'][0]
    target = url + '/revisions/' + discarded['id']
    assert admin.post(target + '/discard', json={'reason': 'Discard test'}).status_code == 200
    successor = admin.post(url + '/revisions', json={'change_reason': 'Second test'}).json()['revisions'][0]
    with app_db.begin() as conn:
        conn.execute(text('UPDATE item_revision SET supersedes_id=:old WHERE id=:new'),
                     {'old': discarded['id'], 'new': successor['id']})
    response = admin.request('DELETE', target, json={'reason': 'Remove test'})
    assert response.status_code == 409, response.text
    assert any(r['id'] == discarded['id'] for r in admin.get(url).json()['revisions'])
    assert admin.get('/api/audit/verify').json()['ok'] is True
