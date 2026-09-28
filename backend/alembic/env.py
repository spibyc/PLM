"""Alembic environment. Migrations run as the schema-owner role (PLM_MIGRATOR_DATABASE_URL),
never as the least-privilege application role."""
import os

from alembic import context
from sqlalchemy import create_engine

from app.models import Base

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("PLM_MIGRATOR_DATABASE_URL") or os.environ.get("PLM_DATABASE_URL")
    if not url:
        raise RuntimeError("PLM_MIGRATOR_DATABASE_URL is not set")
    return url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
