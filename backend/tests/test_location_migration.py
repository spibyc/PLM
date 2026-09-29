"""Exercise the new migration on an existing installation, independently of old downgrades."""
import os
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.conftest import _super_exec, PW


def test_existing_installation_location_migration(monkeypatch):
    name = f'qplm_location_mig_{uuid.uuid4().hex[:8]}'
    _super_exec(f'CREATE DATABASE {name} OWNER qplm_owner')
    for ext in ('citext', 'pg_trgm', 'pgcrypto'):
        _super_exec(f'CREATE EXTENSION IF NOT EXISTS {ext}', name)
    host = os.environ['PLM_MIGRATOR_DATABASE_URL'].rsplit('@', 1)[1].rsplit('/', 1)[0]
    url = f'postgresql+psycopg://qplm_owner:{PW}@{host}/{name}'
    monkeypatch.setenv('PLM_MIGRATOR_DATABASE_URL', url)
    cfg = Config(str(Path(__file__).parent.parent / 'alembic.ini'))
    cfg.set_main_option('script_location', str(Path(__file__).parent.parent / 'alembic'))
    eng = create_engine(url)
    try:
        command.upgrade(cfg, '0006_document_control')
        uid, loc_id = uuid.uuid4(), uuid.uuid4()
        with eng.begin() as c:
            c.execute(text("INSERT INTO role(id, code, name, is_system) VALUES (gen_random_uuid(), 'ADMIN', 'Admin', true)"))
            c.execute(text("""INSERT INTO app_user(id, username, full_name, password_hash, is_active, failed_attempts)
                VALUES (:id, 'migration-test', 'Migration Test', 'unused', true, 0)"""), {'id': uid})
            c.execute(text("""INSERT INTO location(id, kind, code, name, path, is_quarantine, is_active, created_by)
                VALUES (:id, 'site', 'OLD', 'Existing site', 'Existing site', false, true, :uid)"""), {'id': loc_id, 'uid': uid})
        command.upgrade(cfg, 'head')
        with eng.connect() as c:
            assert c.execute(text("SELECT created_by FROM location WHERE id=:id"), {'id': loc_id}).scalar_one() == uid
            assert c.execute(text("SELECT count(*) FROM location WHERE system_key='unallocated' AND is_active")).scalar_one() == 1
            assert c.execute(text("SELECT count(*) FROM role_permission WHERE permission='location:delete'")).scalar_one() == 1
        command.downgrade(cfg, '0006_document_control')
        command.upgrade(cfg, 'head')
        with eng.connect() as c:
            assert c.execute(text('SELECT count(*) FROM location')).scalar_one() == 2
    finally:
        eng.dispose()
        _super_exec(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')
