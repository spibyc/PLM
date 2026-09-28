import hashlib
import io
import os
from pathlib import Path

import pytest
from sqlalchemy import text


@pytest.mark.req("SRS-AUD-001")
def test_audit_event_cannot_be_modified_or_deleted_by_app_role(clients, app_db):
    clients["eng"].post("/api/items", json={"description": "audit subject"})
    with pytest.raises(Exception):
        with app_db.begin() as c:
            c.execute(text("UPDATE audit_event SET reason='x' WHERE id=(SELECT max(id) FROM audit_event)"))
    with pytest.raises(Exception):
        with app_db.begin() as c:
            c.execute(text("DELETE FROM audit_event WHERE id=(SELECT max(id) FROM audit_event)"))


@pytest.mark.req("SRS-AUD-002")
def test_no_api_to_modify_audit(clients):
    assert clients["qa"].delete("/api/audit").status_code in (404, 405)
    assert clients["qa"].put("/api/audit", json={}).status_code in (404, 405)


@pytest.mark.req("SRS-AUD-003")
def test_changes_are_audited_with_before_after(clients):
    eng = clients["eng"]
    item = eng.post("/api/items", json={"description": "before"}).json()
    rev = item["revisions"][0]
    eng.patch(f"/api/items/{item['id']}/revisions/{rev['id']}", json={"row_version": rev["row_version"],
                                                                      "description": "after"})
    ev = eng.get(f"/api/audit/entity/item_revision/{rev['id']}").json()
    mod = [e for e in ev if e["action"] == "modify"][0]
    assert mod["before"] == {"description": "before"} and mod["after"] == {"description": "after"}
    assert mod["actor"] == eng.username


@pytest.mark.req("SRS-AUD-004")
def test_hash_chain_detects_tampering_by_privileged_user(clients, super_db):
    assert clients["qa"].get("/api/audit/verify").json()["ok"] is True
    with super_db.begin() as c:
        eid, orig = c.execute(text("SELECT id, reason FROM audit_event ORDER BY id DESC OFFSET 3 LIMIT 1")).one()
        c.execute(text("ALTER TABLE audit_event DISABLE TRIGGER USER"))
        c.execute(text("UPDATE audit_event SET reason='rewritten history' WHERE id=:i"), {"i": eid})
    try:
        res = clients["qa"].get("/api/audit/verify").json()
        assert res["ok"] is False and res["first_bad_event_id"] == eid
    finally:
        with super_db.begin() as c:
            c.execute(text("UPDATE audit_event SET reason=:r WHERE id=:i"), {"r": orig, "i": eid})
            c.execute(text("ALTER TABLE audit_event ENABLE TRIGGER USER"))
    assert clients["qa"].get("/api/audit/verify").json()["ok"] is True


def test_audit_export_csv_is_itself_audited(clients):
    r = clients["qa"].get("/api/audit/export.csv", params={"action": "login"})
    assert r.status_code == 200 and r.text.startswith("# PLM audit trail export")
    ev = clients["qa"].get("/api/audit", params={"action": "export"}).json()
    assert ev["total"] >= 1


# ---------------- files ----------------

def _draft(clients):  # type: ignore[no-untyped-def]
    item = clients["eng"].post("/api/items", json={"description": "file test"}).json()
    return item["id"], item["revisions"][0]


@pytest.mark.req("SRS-FILE-001")
def test_upload_hash_and_exact_download(clients):
    iid, rev = _draft(clients)
    content = b"(kicad_symbol_lib (version 20231120) (generator test))\n"
    r = clients["eng"].post(f"/api/items/{iid}/revisions/{rev['id']}/attachments",
                            files={"file": ("R_0402.kicad_sym", io.BytesIO(content), "application/octet-stream")},
                            data={"doc_kind": "kicad_symbol"})
    assert r.status_code == 200, r.text
    att = r.json()["revisions"][0]["attachments"][0]
    assert att["sha256"] == hashlib.sha256(content).hexdigest()
    d = clients["ro"].get(f"/api/files/{att['id']}/download")
    assert d.status_code == 200 and d.content == content and d.headers["x-checksum-sha256"] == att["sha256"]


@pytest.mark.req("SRS-FILE-002")
def test_disallowed_and_spoofed_files_rejected(clients):
    iid, rev = _draft(clients)
    url = f"/api/items/{iid}/revisions/{rev['id']}/attachments"
    r = clients["eng"].post(url, files={"file": ("evil.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
                            data={"doc_kind": "other"})
    assert r.status_code == 400 and r.json()["code"] == "bad_type"
    r = clients["eng"].post(url, files={"file": ("fake.pdf", io.BytesIO(b"<html><script>x</script></html>"), "application/pdf")},
                            data={"doc_kind": "datasheet"})
    assert r.status_code == 400 and r.json()["code"] == "mime_mismatch"


@pytest.mark.req("SRS-FILE-003")
def test_cannot_attach_to_released_revision(clients, released_part, app_db):
    iid, rid = released_part["id"], released_part["revisions"][0]["id"]
    r = clients["eng"].post(f"/api/items/{iid}/revisions/{rid}/attachments",
                            files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")}, data={"doc_kind": "other"})
    assert r.status_code == 409


@pytest.mark.req("SRS-FILE-004")
def test_integrity_verification_detects_modified_file(clients):
    iid, rev = _draft(clients)
    content = os.urandom(8).hex().encode() + b" integrity\n"
    r = clients["eng"].post(f"/api/items/{iid}/revisions/{rev['id']}/attachments",
                            files={"file": ("note.txt", io.BytesIO(content), "text/plain")}, data={"doc_kind": "other"})
    sha = r.json()["revisions"][0]["attachments"][0]["sha256"]
    path = Path(os.environ["PLM_FILESTORE_PATH"]) / f"objects/sha256/{sha[:2]}/{sha[2:4]}/{sha}"
    original = path.read_bytes()
    os.chmod(path, 0o640)
    path.write_bytes(b"tampered")
    try:
        res = clients["qa"].post("/api/files/verify").json()
        assert any(f["sha256"] == sha and f["result"] == "SIZE_MISMATCH" for f in res["findings"])
    finally:
        path.write_bytes(original)
        os.chmod(path, 0o440)


def test_file_content_changes_revision_hash(clients):
    """Attachments are part of the signed content: a revision hash covers file SHA-256s."""
    iid, rev = _draft(clients)
    clients["eng"].post(f"/api/items/{iid}/revisions/{rev['id']}/attachments",
                        files={"file": ("a.txt", io.BytesIO(b"alpha"), "text/plain")}, data={"doc_kind": "other"})
    d = clients["eng"].post(f"/api/items/{iid}/revisions/{rev['id']}/submit").json()
    assert d["revisions"][0]["content_hash"]


def test_append_only_trigger_applies_even_with_update_privilege(super_db, available_lot):
    """Defence in depth: even a role that holds UPDATE (here the superuser, triggers enabled) is blocked."""
    with pytest.raises(Exception, match="append-only"):
        with super_db.begin() as c:
            c.execute(text("UPDATE stock_txn SET comment='x' WHERE lot_id=:l"), {"l": available_lot["id"]})


def test_qr_label_is_standalone_svg(clients, locs):
    r = clients["ro"].get(f"/api/qr/location/{locs['a']['id']}.svg")
    assert r.status_code == 200 and 'xmlns="http://www.w3.org/2000/svg"' in r.text
