import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AuthToken, Tenant, User, now

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return ph.verify(encoded, password)
    except Exception:
        return False


def token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(id=token_hash(raw), user_id=user.id, expires_at=now() + timedelta(days=7)))
    return raw


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    raw = session_token
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1]
    if not raw:
        raise HTTPException(401, "Autenticação necessária")
    token = db.get(AuthToken, token_hash(raw))
    if not token or token.expires_at.replace(tzinfo=token.expires_at.tzinfo or now().tzinfo) < now():
        raise HTTPException(401, "Sessão inválida ou expirada")
    user = db.get(User, token.user_id)
    tenant = db.get(Tenant, user.tenant_id) if user else None
    if not user or not user.is_active or user.deleted_at or not tenant or not tenant.is_active or tenant.deleted_at:
        raise HTTPException(403, "Usuário inativo")
    return user


def lab_admin(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "lab_admin"}:
        raise HTTPException(403, "Permissão de laboratório necessária")
    return user
