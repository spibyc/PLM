import pytest
from sqlalchemy import text

from tests.conftest import sign


@pytest.mark.req("SRS-ITEM-001")
def test_full_release_workflow_records_signatures(released_part):
    rev = released_part["revisions"][0]
    assert rev["status"] == "Released" and rev["is_current_released"]
    meanings = [s["meaning"] for s in rev["signatures"]]
    assert meanings == ["Engineering Approved", "Quality Approved", "Released for Production"]
    assert all(s["content_hash"] == rev["content_hash"] for s in rev["signatures"])
    assert [t["to"] for t in rev["transitions"]] == ["Under Review", "Approved", "Released"]


@pytest.mark.req("SRS-ITEM-002")
def test_released_revision_cannot_be_edited_via_api(clients, released_part):
    iid, rev = released_part["id"], released_part["revisions"][0]
    r = clients["eng"].patch(f"/api/items/{iid}/revisions/{rev['id']}",
                             json={"row_version": rev["row_version"], "description": "tampered"})
    assert r.status_code == 409 and r.json()["code"] == "locked"


@pytest.mark.req("SRS-ITEM-003")
def test_released_revision_cannot_be_edited_via_direct_sql(released_part, app_db):
    rid = released_part["revisions"][0]["id"]
    with pytest.raises(Exception, match="cannot be changed"):
        with app_db.begin() as c:
            c.execute(text("UPDATE item_revision SET description='tampered' WHERE id=:i"), {"i": rid})


@pytest.mark.req("SRS-ITEM-004")
def test_controlled_records_cannot_be_deleted(released_part, app_db):
    with pytest.raises(Exception):
        with app_db.begin() as c:
            c.execute(text("DELETE FROM item_revision WHERE id=:i"), {"i": released_part["revisions"][0]["id"]})


@pytest.mark.req("SRS-ITEM-005")
def test_new_revision_supersedes_previous_on_release(clients, released_part):
    eng, eng2, qa = clients["eng"], clients["eng2"], clients["qa"]
    iid = released_part["id"]
    assert eng.post(f"/api/items/{iid}/revisions", json={"change_reason": "x"}).status_code == 422
    r = eng.post(f"/api/items/{iid}/revisions", json={"change_reason": "Tolerance change per ECO-TEST"})
    assert r.status_code == 200
    new = r.json()["revisions"][0]
    assert new["revision_label"] == "B" and new["status"] == "Draft"
    assert eng.post(f"/api/items/{iid}/revisions", json={"change_reason": "second"}).status_code == 409
    r = eng.patch(f"/api/items/{iid}/revisions/{new['id']}", json={"row_version": new["row_version"], "value": "1k 0.1%"})
    assert r.status_code == 200
    eng.post(f"/api/items/{iid}/revisions/{new['id']}/submit")
    base = f"/api/items/{iid}/revisions/{new['id']}/sign"
    sign(eng2, base, "Engineering Approved")
    sign(qa, base, "Quality Approved")
    detail = sign(qa, base, "Released for Production").json()
    by_label = {r["revision_label"]: r for r in detail["revisions"]}
    assert by_label["B"]["status"] == "Released" and by_label["A"]["status"] == "Superseded"
    assert by_label["A"]["value"] == "1k"  # history preserved


@pytest.mark.req("SRS-ITEM-006")
def test_rejection_returns_to_draft_and_requires_comment(clients):
    eng, qa = clients["eng"], clients["qa"]
    item = eng.post("/api/items", json={"description": "reject me"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    assert sign(qa, f"/api/items/{iid}/revisions/{rid}/sign", "Rejected").status_code == 400
    r = sign(qa, f"/api/items/{iid}/revisions/{rid}/sign", "Rejected", "Package wrong")
    assert r.json()["revisions"][0]["status"] == "Draft"


@pytest.mark.req("SRS-ITEM-007")
def test_signature_blocked_if_reviewed_content_differs(clients):
    eng, eng2 = clients["eng"], clients["eng2"]
    item = eng.post("/api/items", json={"description": "hash test"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    r = sign(eng2, f"/api/items/{iid}/revisions/{rid}/sign", "Engineering Approved", content_hash="0" * 64)
    assert r.status_code == 409 and r.json()["code"] == "hash_mismatch"


@pytest.mark.req("SRS-ITEM-008")
def test_wrong_password_blocks_signature(clients):
    eng, eng2 = clients["eng"], clients["eng2"]
    item = eng.post("/api/items", json={"description": "reauth test"}).json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    eng.post(f"/api/items/{iid}/revisions/{rid}/submit")
    r = eng2.post(f"/api/items/{iid}/revisions/{rid}/sign", json={"meaning": "Engineering Approved", "password": "nope"})
    assert r.status_code == 401 and r.json()["code"] == "reauth_failed"


def test_optimistic_concurrency_on_draft_edit(clients):
    eng = clients["eng"]
    item = eng.post("/api/items", json={"description": "occ"}).json()
    iid, rev = item["id"], item["revisions"][0]
    assert eng.patch(f"/api/items/{iid}/revisions/{rev['id']}", json={"row_version": rev["row_version"], "value": "a"}).status_code == 200
    r = eng.patch(f"/api/items/{iid}/revisions/{rev['id']}", json={"row_version": rev["row_version"], "value": "b"})
    assert r.status_code == 409 and r.json()["code"] == "stale"


def test_aml_proposer_cannot_self_approve(clients):
    eng = clients["eng"]
    item = eng.post("/api/items", json={"description": "aml sod"}).json()
    aml = eng.post(f"/api/items/{item['id']}/aml", json={"manufacturer": "TI", "mpn": "SOD-TEST-1"}).json()["aml"][0]
    r = eng.post(f"/api/items/{item['id']}/aml/{aml['id']}/sign", json={"meaning": "AML Approved", "password": "x"})
    assert r.status_code == 403
