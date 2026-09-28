"""Test harness: a real PostgreSQL database, migrated with Alembic as the owner role, and the application
connected as the least-privilege qplm_app role, exactly as in production.

Requires PLM_TEST_SUPERUSER_URL (default postgresql+psycopg://postgres:postgres@localhost/postgres)
pointing at a disposable PostgreSQL 16 cluster.
"""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

SUPER = os.environ.get("PLM_TEST_SUPERUSER_URL", "postgresql+psycopg://postgres:postgres@localhost/postgres")
PW = "Test-Passw0rd-123"
DBNAME = f"qplm_test_{uuid.uuid4().hex[:8]}"
HOST = SUPER.rsplit("@", 1)[1].rsplit("/", 1)[0]


def _super_exec(sql: str, db: str = "postgres") -> None:
    eng = create_engine(SUPER.rsplit("/", 1)[0] + f"/{db}", isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(sql))
    eng.dispose()


def pytest_configure(config):  # type: ignore[no-untyped-def]
    _super_exec("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='qplm_owner') THEN CREATE ROLE qplm_owner LOGIN; END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='qplm_app') THEN CREATE ROLE qplm_app LOGIN; END IF;
        END $$""")
    _super_exec(f"ALTER ROLE qplm_owner LOGIN PASSWORD '{PW}'")
    _super_exec(f"ALTER ROLE qplm_app LOGIN PASSWORD '{PW}'")
    _super_exec(f"CREATE DATABASE {DBNAME} OWNER qplm_owner")
    for ext in ("citext", "pg_trgm", "pgcrypto"):
        _super_exec(f"CREATE EXTENSION IF NOT EXISTS {ext}", DBNAME)
    os.environ["PLM_MIGRATOR_DATABASE_URL"] = f"postgresql+psycopg://qplm_owner:{PW}@{HOST}/{DBNAME}"
    os.environ["PLM_DATABASE_URL"] = f"postgresql+psycopg://qplm_app:{PW}@{HOST}/{DBNAME}"
    os.environ["PLM_TEST_DB_SUPER_URL"] = SUPER.rsplit("/", 1)[0] + f"/{DBNAME}"
    os.environ["PLM_COOKIE_SECURE"] = "false"
    os.environ["PLM_ENVIRONMENT"] = "test"
    os.environ["PLM_LOGIN_RATE_LIMIT_PER_IP"] = "100000"
    os.environ["PLM_FILESTORE_PATH"] = f"/tmp/{DBNAME}-files"
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    command.upgrade(cfg, "head")
    from app.db import new_session
    from app.services.auth import bootstrap_roles

    with new_session() as db:
        bootstrap_roles(db)
        db.commit()


def pytest_unconfigure(config):  # type: ignore[no-untyped-def]
    from app.db import reset_engine

    reset_engine()
    if not os.environ.get("PLM_TEST_KEEP_DB"):
        _super_exec(f"DROP DATABASE IF EXISTS {DBNAME} WITH (FORCE)")


@pytest.fixture(scope="session")
def app():  # type: ignore[no-untyped-def]
    from app.main import create_app

    return create_app()


def _mk_user(roles: list[str]) -> str:
    from app.context import Actor
    from app.db import new_session
    from app.services.auth import create_user

    name = f"u{uuid.uuid4().hex[:10]}"
    with new_session() as db:
        create_user(db, Actor.system("test"), name, f"Test {name}", None, PW, roles)
        db.commit()
    return name


class Client:
    """A logged-in browser-like client (own cookie jar + CSRF token)."""

    def __init__(self, app, username: str):  # type: ignore[no-untyped-def]
        from fastapi.testclient import TestClient

        self.username = username
        self.c = TestClient(app)
        self.c.__enter__()
        r = self.c.post("/api/auth/login", json={"username": username, "password": PW})
        assert r.status_code == 200, r.text
        self.me = r.json()
        self.c.headers["X-CSRF-Token"] = self.me["csrf_token"]

    def __getattr__(self, k):  # type: ignore[no-untyped-def]
        return getattr(self.c, k)


@pytest.fixture(scope="session")
def users():  # type: ignore[no-untyped-def]
    return {
        "admin": _mk_user(["ADMIN"]), "eng": _mk_user(["ENGINEERING"]), "eng2": _mk_user(["ENGINEERING"]),
        "qa": _mk_user(["QUALITY"]), "prod": _mk_user(["PRODUCTION"]), "buyer": _mk_user(["PURCHASING"]), "ro": _mk_user(["READONLY"]),
    }


@pytest.fixture(scope="session")
def clients(app, users):  # type: ignore[no-untyped-def]
    return {k: Client(app, v) for k, v in users.items()}


@pytest.fixture
def super_db():  # type: ignore[no-untyped-def]
    eng = create_engine(os.environ["PLM_TEST_DB_SUPER_URL"])
    yield eng
    eng.dispose()


@pytest.fixture
def app_db():  # type: ignore[no-untyped-def]
    eng = create_engine(os.environ["PLM_DATABASE_URL"])
    yield eng
    eng.dispose()


def sign(client, url: str, meaning: str, comment: str | None = None, **extra):  # type: ignore[no-untyped-def]
    return client.post(url, json={"meaning": meaning, "password": PW, "comment": comment, **extra})


@pytest.fixture
def released_part(clients):  # type: ignore[no-untyped-def]
    """A component released through the full controlled workflow, with an approved AML entry."""
    eng, eng2, qa = clients["eng"], clients["eng2"], clients["qa"]
    r = eng.post("/api/items", json={"description": f"RES test {uuid.uuid4().hex[:6]}", "value": "1k",
                                     "package": "0402"})
    assert r.status_code == 200, r.text
    item = r.json()
    iid, rid = item["id"], item["revisions"][0]["id"]
    assert eng.post(f"/api/items/{iid}/revisions/{rid}/submit").status_code == 200
    base = f"/api/items/{iid}/revisions/{rid}/sign"
    assert sign(eng2, base, "Engineering Approved").status_code == 200
    assert sign(qa, base, "Quality Approved").status_code == 200
    r = sign(qa, base, "Released for Production")
    assert r.status_code == 200, r.text
    r = eng.post(f"/api/items/{iid}/aml", json={"manufacturer": "Yageo", "mpn": f"RC-{uuid.uuid4().hex[:8]}"})
    aml = r.json()["aml"][0]
    r = qa.post(f"/api/items/{iid}/aml/{aml['id']}/sign", json={"meaning": "AML Approved", "password": PW})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def locs(clients):  # type: ignore[no-untyped-def]
    admin = clients["admin"]
    seg = uuid.uuid4().hex[:6].upper()
    site = admin.post("/api/locations", json={"kind": "site", "segment": f"S{seg}", "name": "Test site"}).json()
    a = admin.post("/api/locations", json={"parent_id": site["id"], "kind": "room", "segment": "A", "name": "Room A"}).json()
    b = admin.post("/api/locations", json={"parent_id": site["id"], "kind": "room", "segment": "B", "name": "Room B"}).json()
    q = admin.post("/api/locations", json={"parent_id": site["id"], "kind": "room", "segment": "Q", "name": "Quarantine",
                                           "is_quarantine": True}).json()
    return {"site": site, "a": a, "b": b, "q": q}


@pytest.fixture
def available_lot(clients, released_part, locs):  # type: ignore[no-untyped-def]
    prod, qa = clients["prod"], clients["qa"]
    r = prod.post("/api/lots", json={"item_id": released_part["id"], "qty": 100, "location_id": locs["a"]["id"],
                                     "manufacturer_part_id": released_part["aml"][0]["manufacturer_part_id"],
                                     "supplier_name": "Test Supplier", "supplier_lot": "SL1"})
    assert r.status_code == 200, r.text
    lot = r.json()
    r = qa.post(f"/api/lots/{lot['id']}/inspect", json={"accept": True, "password": PW, "comment": "OK"})
    assert r.status_code == 200, r.text
    return r.json()
