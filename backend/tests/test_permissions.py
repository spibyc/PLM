import pytest

from tests.conftest import sign


@pytest.mark.req("SRS-RBAC-001")
def test_read_only_cannot_create_items(clients):
    assert clients["ro"].post("/api/items", json={"description": "x"}).status_code == 403


@pytest.mark.req("SRS-RBAC-002")
def test_unauthorised_user_cannot_approve(clients):
    eng, prod = clients["eng"], clients["prod"]
    item = eng.post("/api/items", json={"description": "perm test"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    r = sign(prod, f"/api/items/{iid}/revisions/{rid}/sign", "Quality Approved")
    assert r.status_code == 403 and r.json()["code"] == "no_signing_authority"
    # Engineering cannot sign the Quality meaning
    r = sign(clients["eng2"], f"/api/items/{iid}/revisions/{rid}/sign", "Quality Approved")
    assert r.status_code == 403


@pytest.mark.req("SRS-RBAC-003")
def test_administrator_has_no_signing_authority(clients):
    eng, admin = clients["eng"], clients["admin"]
    item = eng.post("/api/items", json={"description": "admin sign test"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    for meaning in ("Engineering Approved", "Quality Approved"):
        assert sign(admin, f"/api/items/{iid}/revisions/{rid}/sign", meaning).status_code == 403


@pytest.mark.req("SRS-RBAC-004")
def test_author_cannot_approve_own_revision(clients):
    eng = clients["eng"]
    item = eng.post("/api/items", json={"description": "sod test"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    r = sign(eng, f"/api/items/{iid}/revisions/{rid}/sign", "Engineering Approved")
    assert r.status_code == 403 and r.json()["code"] == "sod"


@pytest.mark.req("SRS-RBAC-005")
def test_admin_cannot_change_own_roles(clients):
    admin = clients["admin"]
    uid = admin.me["id"]
    r = admin.put(f"/api/users/{uid}/roles", json={"roles": ["ADMIN", "QUALITY"]})
    assert r.status_code == 403 and r.json()["code"] == "self_grant"


def test_role_change_is_audited_and_revokes_sessions(app, clients):
    from tests.conftest import Client, _mk_user

    name = _mk_user(["READONLY"])
    victim = Client(app, name)
    users = clients["admin"].get("/api/users").json()
    uid = next(u["id"] for u in users if u["username"] == name)
    r = clients["admin"].put(f"/api/users/{uid}/roles", json={"roles": ["PRODUCTION"]})
    assert r.status_code == 200 and r.json()["roles"] == ["PRODUCTION"]
    assert victim.get("/api/auth/me").status_code == 401  # session revoked on privilege change
    ev = clients["qa"].get("/api/audit", params={"action": "permission_change", "entity_id": uid}).json()
    assert ev["items"][0]["after"] == {"roles": ["PRODUCTION"]}
