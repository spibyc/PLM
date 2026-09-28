import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.req("SRS-SYS-001")
def test_migrations_upgrade_downgrade_upgrade():
    from alembic import command
    from alembic.config import Config

    from tests.conftest import PW, _super_exec

    name = f"qplm_mig_{uuid.uuid4().hex[:8]}"
    _super_exec(f"CREATE DATABASE {name} OWNER qplm_owner")
    for ext in ("citext", "pg_trgm", "pgcrypto"):
        _super_exec(f"CREATE EXTENSION IF NOT EXISTS {ext}", name)
    host = os.environ["PLM_MIGRATOR_DATABASE_URL"].rsplit("@", 1)[1].rsplit("/", 1)[0]
    url = f"postgresql+psycopg://qplm_owner:{PW}@{host}/{name}"
    old = os.environ["PLM_MIGRATOR_DATABASE_URL"]
    os.environ["PLM_MIGRATOR_DATABASE_URL"] = url
    try:
        cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        eng = create_engine(url)
        with eng.connect() as c:
            from app.version import EXPECTED_SCHEMA_REVISION

            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == EXPECTED_SCHEMA_REVISION
        eng.dispose()
    finally:
        os.environ["PLM_MIGRATOR_DATABASE_URL"] = old
        _super_exec(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


def test_version_and_ready_endpoints(clients):
    v = clients["ro"].get("/api/version").json()
    assert v["schema_revision"] == v["expected_schema_revision"]
    assert clients["ro"].get("/api/ready").status_code == 200


@pytest.mark.req("SRS-SYS-001")
def test_api_refuses_to_start_on_schema_mismatch(monkeypatch):
    import asyncio

    import app.main as main

    monkeypatch.setattr(main, "EXPECTED_SCHEMA_REVISION", "9999_future")
    app = main.create_app()

    async def start():
        async with main.lifespan(app):
            pass

    with pytest.raises(RuntimeError, match="does not match"):
        asyncio.run(start())
