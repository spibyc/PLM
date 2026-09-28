import datetime as dt
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, db_now, uuid_pk


class AuditEvent(Base):
    """Append-only, hash-chained. UPDATE/DELETE are blocked by trigger for every role."""

    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, default=uuid.uuid4)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"))
    actor_username: Mapped[str] = mapped_column(String(200))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    request_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    entity_label: Mapped[str | None] = mapped_column(String(300))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_occurred", "occurred_at"),
        Index("ix_audit_actor", "actor_id"),
    )


class Signature(Base):
    """Electronic signature bound to an object, a review cycle and the content hash signed. Insert-only."""

    __tablename__ = "signature"
    id: Mapped[uuid.UUID] = uuid_pk()
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    review_cycle: Mapped[int] = mapped_column(Integer, default=0)
    meaning: Mapped[str] = mapped_column(String(64))
    signer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"))
    signer_name: Mapped[str] = mapped_column(String(200))
    signed_at: Mapped[dt.datetime] = db_now()
    content_hash: Mapped[str | None] = mapped_column(String(64))
    comment: Mapped[str | None] = mapped_column(Text)
    auth_method: Mapped[str] = mapped_column(String(32), default="password")
    __table_args__ = (
        UniqueConstraint("object_type", "object_id", "review_cycle", "meaning", "signer_id"),
        Index("ix_signature_object", "object_type", "object_id"),
    )


class StateTransition(Base):
    __tablename__ = "state_transition"
    id: Mapped[uuid.UUID] = uuid_pk()
    object_type: Mapped[str] = mapped_column(String(64))
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"))
    at: Mapped[dt.datetime] = db_now()
    reason: Mapped[str | None] = mapped_column(Text)
    signature_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("signature.id"))
    __table_args__ = (Index("ix_transition_object", "object_type", "object_id"),)
