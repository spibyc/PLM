import pytest

from tests.conftest import PW, Client, _mk_user


@pytest.mark.req("SRS-AUTH-001")
def test_login_logout_and_me(app, users):
    c = Client(app, users["ro"])
    assert c.get("/api/auth/me").json()["username"] == users["ro"]
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


@pytest.mark.req("SRS-AUTH-002")
def test_bad_password_rejected_and_audited(app, clients, users):
    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        r = tc.post("/api/auth/login", json={"username": users["ro"], "password": "wrong"})
        assert r.status_code == 401
    ev = clients["qa"].get("/api/audit", params={"action": "login_failed", "actor_name": users["ro"]}).json()
    assert ev["total"] >= 1


@pytest.mark.req("SRS-AUTH-003")
def test_lockout_after_repeated_failures(app):
    from fastapi.testclient import TestClient

    name = _mk_user(["READONLY"])
    with TestClient(app) as tc:
        for _ in range(5):
            tc.post("/api/auth/login", json={"username": name, "password": "wrong"})
        r = tc.post("/api/auth/login", json={"username": name, "password": PW})
        assert r.status_code == 401 and r.json()["code"] == "locked"


@pytest.mark.req("SRS-AUTH-004")
def test_csrf_required_for_unsafe_methods(app, users):
    c = Client(app, users["eng"])
    del c.c.headers["X-CSRF-Token"]
    r = c.post("/api/items", json={"description": "x"})
    assert r.status_code == 403 and r.json()["code"] == "csrf"


@pytest.mark.req("SRS-AUTH-005")
def test_unauthenticated_requests_rejected(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        assert tc.get("/api/items").status_code == 401
        assert tc.get("/api/audit").status_code == 401


def test_weak_password_rejected(clients):
    r = clients["admin"].post("/api/users", json={"username": "weakling", "full_name": "Weak", "password": "short"})
    assert r.status_code == 400 and r.json()["code"] == "weak_password"
