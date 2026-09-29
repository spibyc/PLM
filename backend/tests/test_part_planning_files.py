import uuid


def test_planning_and_shared_files_leave_released_revision_unchanged(clients, released_part):
    eng, ro = clients['eng'], clients['ro']
    url = f"/api/items/{released_part['id']}"
    original = eng.get(url).json()
    body = {'min_stock': 12, 'reason': 'Set reorder threshold'}
    assert ro.put(url + '/planning', json=body).status_code == 403
    assert eng.put(url + '/planning', json={**body, 'min_stock': -1}).status_code == 422
    response = eng.put(url + '/planning', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['min_stock'] == 12
    assert response.json()['revisions'] == original['revisions']
    content = b'Supporting information for this part\n'
    upload = {'files': {'file': ('support.txt', content, 'text/plain')}, 'data': {'doc_kind': 'other'}}
    assert ro.post(url + '/attachments', **upload).status_code == 403
    assert eng.post(f'/api/items/{uuid.uuid4()}/attachments', **upload).status_code == 404
    response = eng.post(url + '/attachments', **upload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['revisions'] == original['revisions']
    assert data['current_released_revision_id'] == original['current_released_revision_id']
    attachment = data['attachments'][0]
    assert ro.get(f"/api/files/{attachment['id']}/download").content == content
    events = eng.get(f"/api/audit/entity/item/{released_part['id']}").json()
    assert any(e['action'] == 'upload' for e in events)
    response = eng.post(url + '/revisions', json={'change_reason': 'Next engineering change'})
    assert response.status_code == 200, response.text
    assert response.json()['attachments'] == data['attachments']


def test_zero_stock_only_below_minimum_when_positive_minimum(clients, released_part):
    eng = clients['eng']
    url = f"/api/items/{released_part['id']}/planning"
    assert eng.put(url, json={'min_stock': 0, 'reason': 'No stocking requirement'}).status_code == 200
    baseline = eng.get('/api/dashboard').json()
    assert eng.put(url, json={'min_stock': 1, 'reason': 'Require one spare'}).status_code == 200
    positive = eng.get('/api/dashboard').json()
    assert positive['below_min_stock'] == baseline['below_min_stock'] + 1
    assert positive['out_of_stock'] == baseline['out_of_stock']
    assert eng.put(url, json={'min_stock': 0, 'reason': 'Remove stocking requirement'}).status_code == 200
    assert eng.get('/api/dashboard').json()['below_min_stock'] == baseline['below_min_stock']
