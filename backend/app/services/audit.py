"""Append-only, hash-chained audit trail.

Events are written in the same database transaction as the change they describe, so a change
cannot commit without its audit event. hash = SHA256(prev_hash || canonical_json(event)).
"""
import datetime as dt
import decimal
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.context import Actor, request_id_var
from app.models import AuditEvent

GENESIS = "0" * 64
_CHAIN_LOCK = 7_130_001


def _default(o: Any) -> Any:
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, (uuid.UUID, decimal.Decimal)):
        return str(o)
    raise TypeError(type(o))


def canonical(obj: Any) -> str:
    return json.dumps(obj, default=_default, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def jsonable(obj: Any) -> Any:
    return json.loads(canonical(obj)) if obj is not None else None


def _payload(e: AuditEvent) -> dict[str, Any]:
    return {
        "event_uuid": str(e.event_uuid),
        "occurred_at": e.occurred_at.astimezone(dt.timezone.utc).isoformat(),
        "actor_id": str(e.actor_id) if e.actor_id else None,
        "actor_username": e.actor_username,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "entity_label": e.entity_label,
        "before": e.before,
        "after": e.after,
        "reason": e.reason,
        "session_id": str(e.session_id) if e.session_id else None,
        "ip": e.ip,
        "request_id": e.request_id,
    }


def compute_hash(prev_hash: str, e: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + canonical(_payload(e))).encode()).hexdigest()


def record(
    db: Session,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    label: str | None = None,
    before: Any = None,
    after: Any = None,
    reason: str | None = None,
) -> AuditEvent:
    # Serialise chain appends for this transaction; released at commit/rollback.
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK})
    prev = db.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    now = db.execute(text("SELECT clock_timestamp()")).scalar_one()
    e = AuditEvent(
        event_uuid=uuid.uuid4(),
        occurred_at=now,
        actor_id=actor.user_id,
        actor_username=actor.username,
        session_id=actor.session_id,
        ip=actor.ip,
        user_agent=actor.user_agent,
        request_id=request_id_var.get(),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_label=label,
        before=jsonable(before),
        after=jsonable(after),
        reason=reason,
        prev_hash=prev or GENESIS,
    )
    e.hash = compute_hash(e.prev_hash, e)
    db.add(e)
    db.flush()
    return e


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def verify_chain(db: Session, batch: int = 5000) -> dict[str, Any]:
    prev = GENESIS
    count = 0
    last_id = 0
    while True:
        rows = db.execute(
            select(AuditEvent).where(AuditEvent.id > last_id).order_by(AuditEvent.id).limit(batch)
        ).scalars().all()
        if not rows:
            break
        for e in rows:
            if e.prev_hash != prev or compute_hash(e.prev_hash, e) != e.hash:
                return {"ok": False, "events_checked": count, "first_bad_event_id": e.id, "head": prev}
            prev = e.hash
            count += 1
            last_id = e.id
    return {"ok": True, "events_checked": count, "first_bad_event_id": None, "head": prev}
