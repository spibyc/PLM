"""Electronic signatures: deliberate, re-authenticated, attributable, bound to content."""
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.errors import Conflict, DomainError, Forbidden
from app.models import Signature, StateTransition
from app.services import audit
from app.services.auth import reauthenticate

MEANING_PERMISSION: dict[str, tuple[str, ...]] = {
    "Engineering Approved": ("sign:engineering_approved",),
    "Quality Approved": ("sign:quality_approved",),
    "Released for Production": ("sign:released",),
    "Rejected": ("sign:engineering_approved", "sign:quality_approved", "sign:released"),
    "NRND Approved": ("sign:quality_approved",),
    "Obsolescence Approved": ("sign:quality_approved",),
    "Prohibition Approved": ("sign:quality_approved",),
    "Material Released": ("sign:material_released",),
    "Material Rejected": ("sign:material_released",),
    "AML Approved": ("sign:aml_approved",),
    "AML Disqualified": ("sign:aml_approved",),
    "Supplier Approved": ("sign:supplier_approved",),
    "Purchase Order Approved": ("sign:po_approved",),
    "BOM Released": ("sign:bom_released",),
    "Build Released": ("sign:build_released",),
    "Serial Released": ("sign:build_released",),
    "Document Released": ("sign:document_released",),
    "Document Obsoleted": ("sign:document_obsolete",),
}
COMMENT_REQUIRED = {"Rejected", "NRND Approved", "Obsolescence Approved", "Prohibition Approved",
                    "Material Rejected", "AML Disqualified", "Document Obsoleted"}


def check_authority(actor: Actor, meaning: str) -> None:
    perms = MEANING_PERMISSION.get(meaning)
    if perms is None:
        raise DomainError(f"Unknown signature meaning '{meaning}'", "bad_meaning")
    if not any(actor.has(p) for p in perms):
        raise Forbidden(f"You do not have authority to sign '{meaning}'", "no_signing_authority")


def sign(
    db: Session, actor: Actor, *, object_type: str, object_id: uuid.UUID, meaning: str, password: str,
    comment: str | None, review_cycle: int = 0, content_hash: str | None = None, label: str | None = None,
) -> Signature:
    check_authority(actor, meaning)
    if meaning in COMMENT_REQUIRED and not (comment and comment.strip()):
        raise DomainError(f"A comment is required for '{meaning}'", "comment_required")
    reauthenticate(db, actor, password)
    sig = Signature(
        object_type=object_type, object_id=object_id, review_cycle=review_cycle, meaning=meaning,
        signer_id=actor.user_id, signer_name=actor.full_name, content_hash=content_hash,
        comment=(comment or None), auth_method="password",
    )
    try:
        with db.begin_nested():
            db.add(sig)
            db.flush()
    except IntegrityError:
        raise Conflict("You have already applied this signature in the current review cycle") from None
    audit.record(db, actor, "sign", object_type, object_id, label,
                 after={"meaning": meaning, "review_cycle": review_cycle, "content_hash": content_hash},
                 reason=comment)
    return sig


def next_event_cycle(db: Session, object_type: str, object_id: uuid.UUID) -> int:
    """For objects without review cycles (lots), each signing event gets its own cycle number so the
    same person can sign the same meaning at different events (e.g. inspection release, later quarantine release)."""
    from sqlalchemy import func

    return int(db.execute(select(func.count()).select_from(Signature).where(
        Signature.object_type == object_type, Signature.object_id == object_id)).scalar_one()) + 1


def transition(db: Session, actor: Actor, object_type: str, object_id: uuid.UUID, frm: str | None, to: str,
               reason: str | None = None, signature_id: uuid.UUID | None = None, label: str | None = None) -> None:
    db.add(StateTransition(object_type=object_type, object_id=object_id, from_status=frm, to_status=to,
                           actor_id=actor.user_id, reason=reason, signature_id=signature_id))
    audit.record(db, actor, "state_change", object_type, object_id, label,
                 before={"status": frm}, after={"status": to}, reason=reason)


def list_for(db: Session, object_type: str, object_id: uuid.UUID) -> list[dict]:
    rows = db.execute(select(Signature).where(Signature.object_type == object_type, Signature.object_id == object_id)
                      .order_by(Signature.signed_at)).scalars()
    return [{"id": str(s.id), "meaning": s.meaning, "signer_name": s.signer_name, "signer_id": str(s.signer_id),
             "signed_at": s.signed_at, "review_cycle": s.review_cycle, "content_hash": s.content_hash,
             "comment": s.comment} for s in rows]


def transitions_for(db: Session, object_type: str, object_id: uuid.UUID) -> list[dict]:
    from app.models import User

    rows = db.execute(select(StateTransition, User.full_name).join(User, User.id == StateTransition.actor_id)
                      .where(StateTransition.object_type == object_type, StateTransition.object_id == object_id)
                      .order_by(StateTransition.at)).all()
    return [{"from": t.from_status, "to": t.to_status, "by": n, "at": t.at, "reason": t.reason} for t, n in rows]
