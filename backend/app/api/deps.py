from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.context import Actor
from app.core.errors import DomainError, Forbidden
from app.db import get_db
from app.services import auth

SESSION_COOKIE = "plm_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str | None:
    # Uvicorn --proxy-headers with --forwarded-allow-ips resolves the real client IP from trusted proxies only.
    return request.client.host if request.client else None


def current_actor(request: Request, db: Session = Depends(get_db)) -> Actor:
    token = request.cookies.get(SESSION_COOKIE)
    resolved = auth.resolve_session(db, token) if token else None
    if resolved is None:
        raise DomainError("Not authenticated or session expired", "unauthenticated", 401)
    sess, user = resolved
    if request.method in UNSAFE:
        sent = request.headers.get("X-CSRF-Token")
        if not sent or sent != sess.csrf_token:
            raise Forbidden("CSRF token missing or invalid", "csrf")
    db.commit()  # persist last_seen_at
    return auth.actor_for(db, user, sess.id, client_ip(request), request.headers.get("user-agent"))


def require(*perms: str) -> Callable[..., Actor]:
    def dep(actor: Actor = Depends(current_actor)) -> Actor:
        missing = [p for p in perms if not actor.has(p)]
        if missing:
            raise Forbidden(f"Missing permission: {', '.join(missing)}")
        return actor

    return dep
