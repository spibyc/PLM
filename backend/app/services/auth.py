import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.config import get_settings
from app.core.errors import Conflict, DomainError, Forbidden, NotFound
from app.core.security import check_password_policy, hash_password, new_token, token_hash, verify_password
from app.db import new_session
from app.models import Role, RolePermission, User, UserRole, UserSession
from app.permissions import DEFAULT_ROLES, PERMISSIONS
from app.services import audit


def _now(db: Session) -> dt.datetime:
    return db.execute(text("SELECT clock_timestamp()")).scalar_one()


def permissions_for(db: Session, user_id: uuid.UUID) -> frozenset[str]:
    rows = db.execute(
        select(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None))
    ).scalars()
    return frozenset(r for r in rows if r in PERMISSIONS)


def roles_for(db: Session, user_id: uuid.UUID) -> list[str]:
    return list(
        db.execute(
            select(Role.code).join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None)).order_by(Role.code)
        ).scalars()
    )


def actor_for(db: Session, user: User, session_id=None, ip=None, ua=None) -> Actor:  # type: ignore[no-untyped-def]
    return Actor(user.id, user.username, user.full_name, permissions_for(db, user.id), session_id, ip, ua)


@dataclass
class LoginResult:
    token: str
    csrf_token: str
    user: User
    session_id: uuid.UUID


def _audit_failure(username: str, ip: str | None, ua: str | None, reason: str, user_id=None) -> None:  # type: ignore[no-untyped-def]
    """Failed logins are recorded in their own transaction (there is no business transaction to join)."""
    with new_session() as s:
        actor = Actor(user_id, username or "(blank)", username or "", frozenset(), None, ip, ua)
        audit.record(s, actor, "login_failed", "session", None, username, reason=reason)
        if user_id is not None:
            s.execute(
                update(User).where(User.id == user_id).values(failed_attempts=User.failed_attempts + 1)
            )
            u = s.get(User, user_id)
            st = get_settings()
            if u and u.failed_attempts >= st.login_max_failures:
                s.execute(
                    update(User).where(User.id == user_id)
                    .values(locked_until=func.clock_timestamp() + dt.timedelta(minutes=st.lockout_minutes))
                )
                audit.record(s, actor, "account_locked", "user", user_id, username,
                             reason=f"{u.failed_attempts} consecutive failed logins")
        s.commit()


def login(db: Session, username: str, password: str, ip: str | None, ua: str | None) -> LoginResult:
    st = get_settings()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    generic = DomainError("Invalid username or password", "invalid_credentials", 401)
    if user is None:
        verify_password(hash_password("x"), password)  # equalise timing
        _audit_failure(username, ip, ua, "unknown user")
        raise generic
    now = _now(db)
    if not user.is_active:
        _audit_failure(username, ip, ua, "inactive account", user.id)
        raise generic
    if user.locked_until and user.locked_until > now:
        _audit_failure(username, ip, ua, "account locked", user.id)
        raise DomainError("Account temporarily locked. Try later or contact an administrator.", "locked", 401)
    if not verify_password(user.password_hash, password):
        _audit_failure(username, ip, ua, "bad password", user.id)
        raise generic
    user.failed_attempts = 0
    user.locked_until = None
    token, csrf = new_token(), new_token()
    sess = UserSession(
        token_hash=token_hash(token), csrf_token=csrf, user_id=user.id,
        expires_at=now + dt.timedelta(hours=st.session_absolute_hours), ip=ip, user_agent=(ua or "")[:400],
    )
    db.add(sess)
    db.flush()
    audit.record(db, actor_for(db, user, sess.id, ip, ua), "login", "session", sess.id, user.username)
    return LoginResult(token, csrf, user, sess.id)


def resolve_session(db: Session, token: str) -> tuple[UserSession, User] | None:
    st = get_settings()
    sess = db.execute(select(UserSession).where(UserSession.token_hash == token_hash(token))).scalar_one_or_none()
    if sess is None or sess.revoked_at is not None:
        return None
    now = _now(db)
    if sess.expires_at <= now or sess.last_seen_at + dt.timedelta(minutes=st.session_idle_minutes) <= now:
        return None
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        return None
    if (now - sess.last_seen_at).total_seconds() > 30:
        sess.last_seen_at = now
    return sess, user


def logout(db: Session, actor: Actor) -> None:
    if actor.session_id:
        db.execute(update(UserSession).where(UserSession.id == actor.session_id)
                   .values(revoked_at=func.clock_timestamp()))
        audit.record(db, actor, "logout", "session", actor.session_id, actor.username)


def reauthenticate(db: Session, actor: Actor, password: str) -> None:
    """Deliberate re-authentication for electronic signatures."""
    user = db.get(User, actor.user_id)
    if user is None or not verify_password(user.password_hash, password):
        _audit_failure(actor.username, actor.ip, actor.user_agent, "signature re-authentication failed",
                       actor.user_id)
        raise DomainError("Re-authentication failed: password incorrect", "reauth_failed", 401)


def _revoke_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
               .values(revoked_at=func.clock_timestamp()))


# ---------------- user administration ----------------

def user_dict(db: Session, u: User) -> dict:
    return {
        "id": str(u.id), "username": u.username, "full_name": u.full_name, "email": u.email,
        "is_active": u.is_active, "roles": roles_for(db, u.id),
        "locked": bool(u.locked_until and u.locked_until > _now(db)), "created_at": u.created_at,
    }


def create_user(db: Session, actor: Actor, username: str, full_name: str, email: str | None,
                password: str, role_codes: list[str]) -> User:
    check_password_policy(password, get_settings().password_min_length)
    if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        raise Conflict("Username already exists")
    u = User(username=username, full_name=full_name, email=email, password_hash=hash_password(password),
             created_by=actor.user_id, password_changed_at=_now(db), is_active=True, failed_attempts=0)
    db.add(u)
    db.flush()
    audit.record(db, actor, "create", "user", u.id, username,
                 after={"username": username, "full_name": full_name, "email": email})
    set_roles(db, actor, u, role_codes, allow_self=True)
    return u


def set_roles(db: Session, actor: Actor, user: User, role_codes: list[str], allow_self: bool = False) -> None:
    if not allow_self and actor.user_id == user.id:
        raise Forbidden("You cannot change your own role assignments", "self_grant")
    wanted = set(role_codes)
    roles = {r.code: r for r in db.execute(select(Role)).scalars()}
    unknown = wanted - roles.keys()
    if unknown:
        raise DomainError(f"Unknown roles: {', '.join(sorted(unknown))}", "unknown_role")
    current = set(roles_for(db, user.id))
    for code in wanted - current:
        db.add(UserRole(user_id=user.id, role_id=roles[code].id, granted_by=actor.user_id))
    for code in current - wanted:
        db.execute(update(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == roles[code].id,
                                          UserRole.revoked_at.is_(None))
                   .values(revoked_at=func.clock_timestamp(), revoked_by=actor.user_id))
    if wanted != current:
        db.flush()
        audit.record(db, actor, "permission_change", "user", user.id, user.username,
                     before={"roles": sorted(current)}, after={"roles": sorted(wanted)})
        _revoke_sessions(db, user.id) if actor.user_id != user.id else None


def set_active(db: Session, actor: Actor, user: User, active: bool, reason: str) -> None:
    if actor.user_id == user.id:
        raise Forbidden("You cannot deactivate your own account")
    if user.is_active != active:
        user.is_active = active
        if not active:
            _revoke_sessions(db, user.id)
        audit.record(db, actor, "activate" if active else "deactivate", "user", user.id, user.username,
                     before={"is_active": not active}, after={"is_active": active}, reason=reason)


def admin_reset_password(db: Session, actor: Actor, user: User, password: str, reason: str) -> None:
    check_password_policy(password, get_settings().password_min_length)
    user.password_hash = hash_password(password)
    user.password_changed_at = _now(db)
    user.failed_attempts = 0
    user.locked_until = None
    _revoke_sessions(db, user.id)
    audit.record(db, actor, "password_reset", "user", user.id, user.username, reason=reason)


def change_own_password(db: Session, actor: Actor, current: str, new: str) -> None:
    user = db.get(User, actor.user_id)
    if user is None:
        raise NotFound("User")
    if not verify_password(user.password_hash, current):
        raise DomainError("Current password incorrect", "reauth_failed", 401)
    check_password_policy(new, get_settings().password_min_length)
    user.password_hash = hash_password(new)
    user.password_changed_at = _now(db)
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None),
                                         UserSession.id != actor.session_id)
               .values(revoked_at=func.clock_timestamp()))
    audit.record(db, actor, "password_change", "user", user.id, user.username)


def bootstrap_roles(db: Session) -> list[str]:
    """Idempotently create default roles. Existing roles' permissions are NOT modified (they may have been
    deliberately configured); new permissions must be granted through a controlled change."""
    created = []
    actor = Actor.system("bootstrap")
    for code, (name, perms) in DEFAULT_ROLES.items():
        if db.execute(select(Role).where(Role.code == code)).scalar_one_or_none():
            continue
        r = Role(code=code, name=name, is_system=True)
        db.add(r)
        db.flush()
        for p in perms:
            db.add(RolePermission(role_id=r.id, permission=p))
        audit.record(db, actor, "create", "role", r.id, code, after={"name": name, "permissions": perms})
        created.append(code)
    db.flush()
    return created
