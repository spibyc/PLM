from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=True)
    return _engine


def new_session() -> Session:
    get_engine()
    assert _factory is not None
    return _factory()


def get_db() -> Iterator[Session]:
    """Request-scoped session. Routes commit explicitly; anything uncommitted is rolled back."""
    db = new_session()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def current_schema_revision(db: Session) -> str | None:
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception:
        db.rollback()
        return None


def reset_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None
