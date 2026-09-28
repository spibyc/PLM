import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.context import Actor
from app.core.errors import NotFound
from app.db import get_db
from app.models import Role, RolePermission, User
from app.permissions import PERMISSIONS
from app.services import auth

router = APIRouter(prefix="/api/users", tags=["users"])
ADMIN = require("users:admin")


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9._-]{3,64}$")
    full_name: str = Field(min_length=2, max_length=200)
    email: str | None = None
    password: str
    roles: list[str] = []


class RolesIn(BaseModel):
    roles: list[str]


class ActiveIn(BaseModel):
    is_active: bool
    reason: str = Field(min_length=3)


class ResetIn(BaseModel):
    password: str
    reason: str = Field(min_length=3)


def _user(db: Session, uid: uuid.UUID) -> User:
    u = db.get(User, uid)
    if u is None:
        raise NotFound("User")
    return u


@router.get("")
def list_users(actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> list[dict]:
    return [auth.user_dict(db, u) for u in db.execute(select(User).order_by(User.username)).scalars()]


@router.get("/roles")
def list_roles(actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for r in db.execute(select(Role).order_by(Role.code)).scalars():
        perms = sorted(db.execute(select(RolePermission.permission).where(RolePermission.role_id == r.id)).scalars())
        out.append({"code": r.code, "name": r.name, "permissions": perms})
    return out


@router.get("/permissions")
def list_permissions(actor: Actor = Depends(ADMIN)) -> dict:
    return PERMISSIONS


@router.post("")
def create_user(body: UserCreate, actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    u = auth.create_user(db, actor, body.username, body.full_name, body.email, body.password, body.roles)
    db.commit()
    return auth.user_dict(db, u)


@router.put("/{uid}/roles")
def set_roles(uid: uuid.UUID, body: RolesIn, actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    u = _user(db, uid)
    auth.set_roles(db, actor, u, body.roles)
    db.commit()
    return auth.user_dict(db, u)


@router.put("/{uid}/active")
def set_active(uid: uuid.UUID, body: ActiveIn, actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    u = _user(db, uid)
    auth.set_active(db, actor, u, body.is_active, body.reason)
    db.commit()
    return auth.user_dict(db, u)


@router.post("/{uid}/reset-password")
def reset_password(uid: uuid.UUID, body: ResetIn, actor: Actor = Depends(ADMIN), db: Session = Depends(get_db)) -> dict:
    u = _user(db, uid)
    auth.admin_reset_password(db, actor, u, body.password, body.reason)
    db.commit()
    return {"ok": True}
