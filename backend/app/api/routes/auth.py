import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, client_ip, current_actor
from app.context import Actor
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db import get_db
from app.models import UserSession
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])
_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit(ip: str | None) -> None:
    """Per-process sliding window. Deploy behind a proxy that also rate-limits for multi-worker setups."""
    key = ip or "?"
    now = time.monotonic()
    dq = _attempts[key]
    while dq and now - dq[0] > 300:
        dq.popleft()
    if len(dq) >= get_settings().login_rate_limit_per_ip:
        raise DomainError("Too many login attempts. Wait a few minutes.", "rate_limited", 429)
    dq.append(now)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


def _me(db: Session, actor: Actor, csrf: str) -> dict:
    return {"id": str(actor.user_id), "username": actor.username, "full_name": actor.full_name,
            "permissions": sorted(actor.permissions), "roles": auth.roles_for(db, actor.user_id),  # type: ignore[arg-type]
            "csrf_token": csrf}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request)
    _rate_limit(ip)
    res = auth.login(db, body.username, body.password, ip, request.headers.get("user-agent"))
    db.commit()
    st = get_settings()
    response.set_cookie(SESSION_COOKIE, res.token, httponly=True, secure=st.cookie_secure, samesite="strict",
                        max_age=st.session_absolute_hours * 3600, path="/")
    actor = auth.actor_for(db, res.user, res.session_id)
    return _me(db, actor, res.csrf_token)


@router.post("/logout")
def logout(response: Response, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)) -> dict:
    auth.logout(db, actor)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(actor: Actor = Depends(current_actor), db: Session = Depends(get_db)) -> dict:
    sess = db.get(UserSession, actor.session_id)
    return _me(db, actor, sess.csrf_token if sess else "")


@router.post("/change-password")
def change_password(body: PasswordChangeIn, actor: Actor = Depends(current_actor), db: Session = Depends(get_db)) -> dict:
    auth.change_own_password(db, actor, body.current_password, body.new_password)
    db.commit()
    return {"ok": True}


