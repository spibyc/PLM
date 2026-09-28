import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_fk_col, uuid_pk


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = db_now()
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Role(Base):
    __tablename__ = "role"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class RolePermission(Base):
    __tablename__ = "role_permission"
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("role.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(100), primary_key=True)


class UserRole(Base):
    """Role grants are never deleted; revocation sets revoked_at so history is preserved."""

    __tablename__ = "user_role"
    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = uuid_fk_col("app_user.id")
    role_id: Mapped[uuid.UUID] = uuid_fk_col("role.id")
    granted_by: Mapped[uuid.UUID | None] = uuid_fk_col("app_user.id", nullable=True)
    granted_at: Mapped[dt.datetime] = db_now()
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = uuid_fk_col("app_user.id", nullable=True)


class UserSession(Base):
    __tablename__ = "user_session"
    id: Mapped[uuid.UUID] = uuid_pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID] = uuid_fk_col("app_user.id", index=True)
    created_at: Mapped[dt.datetime] = db_now()
    last_seen_at: Mapped[dt.datetime] = db_now()
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class NumberSequence(Base):
    __tablename__ = "number_sequence"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(32))
    width: Mapped[int] = mapped_column(Integer)
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("prefix"),)
