import threading
import uuid

import pytest
from sqlalchemy import text

from tests.conftest import PW


@pytest.mark.req("SRS-INV-001")
def test_receipt_requires_released_item(clients, locs):
    item = clients["eng"].post("/api/items", json={"description": "unreleased"}).json()
    r = clients["prod"].post("/api/lots", json={"item_id": item["id"], "qty": 5, "location_id": locs["a"]["id"]})
    assert r.status_code == 409 and r.json()["code"] == "not_released"


@pytest.mark.req("SRS-INV-002")
def test_receipt_requires_approved_aml_part(clients, released_part, locs):
    r = clients["prod"].post("/api/lots", json={"item_id": released_part["id"], "qty": 5,
                                                "location_id": locs["a"]["id"]})
    assert r.status_code == 400 and r.json()["code"] == "mpn_required"


@pytest.mark.req("SRS-INV-003")
def test_lot_pending_inspection_cannot_be_issued(clients, released_part, locs):
    lot = clients["prod"].post("/api/lots", json={
        "item_id": released_part["id"], "qty": 10, "location_id": locs["a"]["id"],
        "manufacturer_part_id": released_part["aml"][0]["manufacturer_part_id"]}).json()
    assert lot["status"] == "Pending Inspection"
    r = clients["prod"].post(f"/api/lots/{lot['id']}/issue", json={"location_id": locs["a"]["id"], "qty": 1,
                                                                    "reference": "WO-1"})
    assert r.status_code == 409 and r.json()["code"] == "not_usable"


@pytest.mark.req("SRS-INV-004")
def test_quarantined_lot_cannot_be_issued_or_reserved(clients, available_lot, locs):
    prod, qa = clients["prod"], clients["qa"]
    lid = available_lot["id"]
    assert prod.post(f"/api/lots/{lid}/quarantine", json={"reason": "NCR-T-1"}).status_code == 200
    body = {"location_id": locs["a"]["id"], "qty": 1, "reference": "BUILD-T"}
    assert prod.post(f"/api/lots/{lid}/issue", json=body).status_code == 409
    assert prod.post(f"/api/lots/{lid}/reserve", json=body).status_code == 409
    # release requires Material Released signature (Quality), not Production
    r = prod.post(f"/api/lots/{lid}/release-quarantine", json={"password": PW, "comment": "Use as is"})
    assert r.status_code == 403
    r = qa.post(f"/api/lots/{lid}/release-quarantine", json={"password": PW, "comment": "Disposition: use as is"})
    assert r.status_code == 200 and r.json()["status"] == "Available"
    assert prod.post(f"/api/lots/{lid}/issue", json=body).status_code == 200


@pytest.mark.req("SRS-INV-005")
def test_stock_in_quarantine_location_cannot_be_issued(clients, available_lot, locs):
    prod = clients["prod"]
    lid = available_lot["id"]
    r = prod.post(f"/api/lots/{lid}/transfer", json={"from_location_id": locs["a"]["id"],
                                                     "to_location_id": locs["q"]["id"], "qty": 10})
    assert r.status_code == 200
    r = prod.post(f"/api/lots/{lid}/issue", json={"location_id": locs["q"]["id"], "qty": 1, "reference": "WO"})
    assert r.status_code == 409


@pytest.mark.req("SRS-INV-006")
def test_negative_stock_rejected(clients, available_lot, locs):
    r = clients["prod"].post(f"/api/lots/{available_lot['id']}/issue",
                             json={"location_id": locs["a"]["id"], "qty": 101, "reference": "WO"})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_stock"


@pytest.mark.req("SRS-INV-007")
def test_database_rejects_negative_balance_directly(available_lot, app_db):
    with pytest.raises(Exception):
        with app_db.begin() as c:
            c.execute(text("UPDATE lot_balance SET qty_on_hand = -1 WHERE lot_id = :l"), {"l": available_lot["id"]})


@pytest.mark.req("SRS-INV-008")
def test_concurrent_issues_never_overdraw(app, users, available_lot, locs):
    """20 concurrent sessions each try to issue 15 from a lot of 100: exactly 6 may succeed."""
    from tests.conftest import Client

    lid, loc = available_lot["id"], locs["a"]["id"]
    clients = [Client(app, users["prod"]) for _ in range(20)]
    results: list[int] = []
    barrier = threading.Barrier(len(clients))

    def worker(c):  # type: ignore[no-untyped-def]
        barrier.wait()
        r = c.post(f"/api/lots/{lid}/issue", json={"location_id": loc, "qty": 15, "reference": "RACE"})
        results.append(r.status_code)

    threads = [threading.Thread(target=worker, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(200) == 6 and results.count(409) == 14
    lot = clients[0].get(f"/api/lots/{lid}").json()
    assert lot["qty_on_hand"] == 10
    issues = [t for t in lot["transactions"] if t["txn_type"] == "ISSUE"]
    # ledger chain is consistent: each 'before' equals the previous 'after'
    chain = sorted(issues, key=lambda t: t["id"])
    for prev, nxt in zip(chain, chain[1:]):
        assert nxt["on_hand_before"] == prev["on_hand_after"]


@pytest.mark.req("SRS-INV-009")
def test_reservation_limits_available_stock(clients, available_lot, locs):
    prod = clients["prod"]
    lid, loc = available_lot["id"], locs["a"]["id"]
    assert prod.post(f"/api/lots/{lid}/reserve", json={"location_id": loc, "qty": 90, "reference": "BUILD-X"}).status_code == 200
    r = prod.post(f"/api/lots/{lid}/issue", json={"location_id": loc, "qty": 20, "reference": "WO"})
    assert r.status_code == 409
    r = prod.post(f"/api/lots/{lid}/release-reservation", json={"location_id": loc, "qty": 90, "reference": "BUILD-X"})
    assert r.status_code == 200
    assert prod.post(f"/api/lots/{lid}/issue", json={"location_id": loc, "qty": 20, "reference": "WO"}).status_code == 200


@pytest.mark.req("SRS-INV-010")
def test_corrections_are_new_transactions_and_ledger_is_append_only(clients, available_lot, locs, app_db):
    prod = clients["prod"]
    lid, loc = available_lot["id"], locs["a"]["id"]
    lot = prod.post(f"/api/lots/{lid}/issue", json={"location_id": loc, "qty": 5, "reference": "WO-TYPO"}).json()
    issue = next(t for t in lot["transactions"] if t["txn_type"] == "ISSUE")
    r = prod.post(f"/api/lots/{lid}/adjust", json={"location_id": loc, "delta": 5, "reason": "Correct mistaken issue",
                                                   "corrects_txn_id": issue["id"]})
    assert r.status_code == 200 and r.json()["qty_on_hand"] == 100
    with pytest.raises(Exception, match="permission denied|append-only"):  # role grant AND trigger
        with app_db.begin() as c:
            c.execute(text("UPDATE stock_txn SET d_on_hand = 0 WHERE id = :i"), {"i": issue["id"]})
    with pytest.raises(Exception):
        with app_db.begin() as c:
            c.execute(text("DELETE FROM stock_txn WHERE id = :i"), {"i": issue["id"]})


@pytest.mark.req("SRS-INV-011")
def test_expired_lot_cannot_be_issued(clients, released_part, locs):
    prod, qa = clients["prod"], clients["qa"]
    lot = prod.post("/api/lots", json={"item_id": released_part["id"], "qty": 10, "location_id": locs["a"]["id"],
                                       "manufacturer_part_id": released_part["aml"][0]["manufacturer_part_id"],
                                       "expiry_date": "2020-01-01"}).json()
    qa.post(f"/api/lots/{lot['id']}/inspect", json={"accept": True, "password": PW, "comment": "ok"})
    r = prod.post(f"/api/lots/{lot['id']}/issue", json={"location_id": locs["a"]["id"], "qty": 1, "reference": "WO"})
    assert r.status_code == 409 and "expired" in r.json()["detail"]


@pytest.mark.req("SRS-INV-012")
def test_prohibited_part_stock_cannot_be_issued(clients, available_lot, released_part, locs):
    qa, prod = clients["qa"], clients["prod"]
    iid, rid = released_part["id"], released_part["revisions"][0]["id"]
    r = qa.post(f"/api/items/{iid}/revisions/{rid}/sign",
                json={"meaning": "Prohibition Approved", "password": PW, "comment": "Counterfeit risk"})
    assert r.status_code == 200
    r = prod.post(f"/api/lots/{available_lot['id']}/issue",
                  json={"location_id": locs["a"]["id"], "qty": 1, "reference": "WO"})
    assert r.status_code == 409


def test_lot_provenance_is_immutable(available_lot, app_db):
    with pytest.raises(Exception, match="immutable"):
        with app_db.begin() as c:
            c.execute(text("UPDATE inventory_lot SET supplier_lot='X' WHERE id=:i"), {"i": available_lot["id"]})


def test_projection_matches_ledger(clients, available_lot):
    assert clients["qa"].get("/api/inventory/verify").json()["ok"] is True


def test_pcs_quantities_must_be_whole(clients, available_lot, locs):
    r = clients["prod"].post(f"/api/lots/{available_lot['id']}/issue",
                             json={"location_id": locs["a"]["id"], "qty": 1.5, "reference": "WO"})
    assert r.status_code == 400


def test_location_hierarchy_enforced(clients, locs):
    r = clients["admin"].post("/api/locations", json={"parent_id": locs["a"]["id"], "kind": "site",
                                                      "segment": uuid.uuid4().hex[:4].upper(), "name": "bad"})
    assert r.status_code == 400 and r.json()["code"] == "hierarchy"
