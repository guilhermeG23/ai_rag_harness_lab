import asyncio
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from argon2 import PasswordHasher
from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = os.environ["DATABASE_URL"]
SYSTEM_ADMIN_USERNAME = os.environ.get("IDENTITY_ADMIN_USER", "admin")
SYSTEM_ADMIN_PASSWORD = os.environ.get("IDENTITY_ADMIN_PASSWORD", "admin")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
ph = PasswordHasher()


def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)
def token_hash(raw: str): return hashlib.sha256(raw.encode()).hexdigest()
def normalize_email(value: str): return value.strip().lower()
def verify(password: str, encoded: str):
    try: return ph.verify(encoded, password)
    except Exception: return False


class Base(DeclarativeBase): pass


class Group(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160))
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="client")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    acl_version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SystemAdmin(Base):
    __tablename__ = "identity_system_admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SystemToken(Base):
    __tablename__ = "identity_system_tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey("identity_system_admins.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Login(BaseModel):
    email: str
    password: str


class AdminLogin(BaseModel):
    username: str
    password: str


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


class UserCreate(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=5, max_length=200)
    role: Literal["client", "admin"] = "client"
    group_id: str | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=5, max_length=200)
    role: Literal["client", "admin"] | None = None
    is_active: bool | None = None
    group_id: str | None = None


class SelfUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=5, max_length=200)


class PasswordUpdate(BaseModel):
    password: str = Field(min_length=5, max_length=200)


def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()


def issue(db: Session, owner_id: str, system: bool = False):
    raw = secrets.token_urlsafe(32)
    model = SystemToken if system else AuthToken
    values = {"id": token_hash(raw), "expires_at": now() + timedelta(days=7)}
    values["admin_id" if system else "user_id"] = owner_id
    db.add(model(**values))
    return raw


def current_user(session_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    token = db.get(AuthToken, token_hash(session_token or ""))
    if not token or token.expires_at.replace(tzinfo=token.expires_at.tzinfo or now().tzinfo) <= now(): raise HTTPException(401, "Sessão inválida ou expirada")
    user = db.get(User, token.user_id)
    group = db.get(Group, user.tenant_id) if user else None
    if not user or not user.is_active or user.deleted_at or not group or not group.is_active or group.deleted_at: raise HTTPException(403, "Acesso desativado")
    return user


def group_admin(user: User = Depends(current_user)):
    if user.role not in {"admin", "lab_admin"}: raise HTTPException(403, "Administrador do grupo necessário")
    return user


def system_admin(identity_admin_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    token = db.get(SystemToken, token_hash(identity_admin_token or ""))
    if not token or token.expires_at.replace(tzinfo=token.expires_at.tzinfo or now().tzinfo) <= now(): raise HTTPException(401, "Sessão administrativa inválida")
    admin = db.get(SystemAdmin, token.admin_id)
    if not admin or not admin.is_active: raise HTTPException(403, "Administrador desativado")
    return admin


def user_dict(user: User, db: Session):
    group = db.get(Group, user.tenant_id)
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": "admin" if user.role in {"admin", "lab_admin"} else "client", "is_active": user.is_active, "group_id": user.tenant_id, "tenant_id": user.tenant_id, "group_name": group.name if group else None, "deleted_at": user.deleted_at, "purge_after": user.purge_after}


def migrate_and_seed():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL"))
        conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS purge_after TIMESTAMPTZ NULL"))
        conn.execute(text("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_name_key"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(160) NOT NULL DEFAULT ''"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS purge_after TIMESTAMPTZ NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (lower(email))"))
    with SessionLocal() as db:
        admin = db.scalar(select(SystemAdmin).where(SystemAdmin.username == SYSTEM_ADMIN_USERNAME))
        if not admin: db.add(SystemAdmin(username=SYSTEM_ADMIN_USERNAME, password_hash=ph.hash(SYSTEM_ADMIN_PASSWORD)))
        seeds = {
            "admin1": [("admin1@admin.com", "Admin 1", "admin1", "admin"), ("teste1@teste.com", "Teste 1", "teste1", "client"), ("teste2@teste.com", "Teste 2", "teste2", "client"), ("teste3@teste.com", "Teste 3", "teste3", "client")],
            "admin2": [("admin2@admin.com", "Admin 2", "admin2", "admin"), ("teste4@teste.com", "Teste 4", "teste4", "client"), ("teste5@teste.com", "Teste 5", "teste5", "client"), ("teste6@teste.com", "Teste 6", "teste6", "client")],
        }
        for group_name, users in seeds.items():
            group = db.scalar(select(Group).where(Group.name == group_name, Group.deleted_at.is_(None)))
            if not group: group = Group(name=group_name); db.add(group); db.flush()
            for email, display_name, password, role in users:
                if not db.scalar(select(User).where(User.email == email)):
                    db.add(User(tenant_id=group.id, email=email, display_name=display_name, password_hash=ph.hash(password), role=role))
        for legacy in db.scalars(select(User).where(User.email.in_(["admin@local.test", "user@local.test"]))): legacy.is_active = False
        db.commit()


def purge_user(db: Session, user: User):
    db.execute(text("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id=:id)"), {"id": user.id})
    db.execute(text("DELETE FROM conversations WHERE user_id=:id"), {"id": user.id})
    db.execute(text("DELETE FROM knowledge_base_permissions WHERE user_id=:id"), {"id": user.id})
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    db.delete(user)


def delete_user_with_mode(db: Session, user: User, mode: str):
    if mode == "immediate": purge_user(db, user)
    elif mode == "30d":
        user.is_active = False; user.deleted_at = now(); user.purge_after = now() + timedelta(days=30)
        db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    else: raise HTTPException(400, "Use mode=immediate ou mode=30d")
    db.commit()


def sweep():
    with SessionLocal() as db:
        for user in list(db.scalars(select(User).where(User.purge_after.is_not(None), User.purge_after <= now()))): purge_user(db, user)
        db.execute(delete(AuthToken).where(AuthToken.expires_at <= now()))
        db.execute(delete(SystemToken).where(SystemToken.expires_at <= now()))
        db.commit()


app = FastAPI(title="Identity Manager", version="1.0.0", docs_url="/api/docs")


@app.on_event("startup")
async def startup():
    migrate_and_seed()
    async def maintenance():
        while True:
            try: sweep()
            except Exception: pass
            await asyncio.sleep(3600)
    asyncio.create_task(maintenance())


@app.get("/health")
def health(): return {"status": "ok", "service": "identity"}


@app.post("/api/v1/auth/login")
def login(payload: Login, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == normalize_email(payload.email)))
    group = db.get(Group, user.tenant_id) if user else None
    if not user or not verify(payload.password, user.password_hash): raise HTTPException(401, "Credenciais inválidas")
    if not user.is_active or user.deleted_at or not group or not group.is_active or group.deleted_at: raise HTTPException(403, "Acesso desativado")
    raw = issue(db, user.id); db.commit()
    response.set_cookie("session_token", raw, httponly=True, samesite="lax", max_age=604800, path="/")
    return {"user": user_dict(user, db)}


@app.post("/api/v1/auth/logout")
def logout(response: Response, session_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if session_token: db.execute(delete(AuthToken).where(AuthToken.id == token_hash(session_token))); db.commit()
    response.delete_cookie("session_token", path="/"); return {"ok": True}


@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)): return user_dict(user, db)


@app.patch("/api/v1/me")
def update_me(payload: SelfUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.display_name is not None: user.display_name = payload.display_name
    if payload.password is not None:
        user.password_hash = ph.hash(payload.password)
        db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    db.commit(); return user_dict(user, db)


@app.get("/api/v1/group/users")
def group_users(admin: User = Depends(group_admin), db: Session = Depends(get_db)):
    return [user_dict(x, db) for x in db.scalars(select(User).where(User.tenant_id == admin.tenant_id).order_by(User.email))]


@app.post("/api/v1/group/users")
def group_create_user(payload: UserCreate, admin: User = Depends(group_admin), db: Session = Depends(get_db)):
    return create_user_record(db, payload, admin.tenant_id)


@app.patch("/api/v1/group/users/{user_id}")
def group_update_user(user_id: str, payload: UserUpdate, admin: User = Depends(group_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target or target.tenant_id != admin.tenant_id: raise HTTPException(404, "Usuário não encontrado")
    return update_user_record(db, target, payload, allow_group=False)


@app.delete("/api/v1/group/users/{user_id}")
def group_delete_user(user_id: str, mode: str = "30d", admin: User = Depends(group_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target or target.tenant_id != admin.tenant_id: raise HTTPException(404, "Usuário não encontrado")
    if target.id == admin.id: raise HTTPException(400, "Não é possível excluir a própria conta por esta tela")
    delete_user_with_mode(db, target, mode); return {"ok": True, "mode": mode}


@app.post("/api/v1/admin/login")
def admin_login(payload: AdminLogin, response: Response, db: Session = Depends(get_db)):
    admin = db.scalar(select(SystemAdmin).where(SystemAdmin.username == payload.username))
    if not admin or not admin.is_active or not verify(payload.password, admin.password_hash): raise HTTPException(401, "Credenciais inválidas")
    raw = issue(db, admin.id, True); db.commit()
    response.set_cookie("identity_admin_token", raw, httponly=True, samesite="lax", max_age=604800, path="/")
    return {"id": admin.id, "username": admin.username}


@app.post("/api/v1/admin/logout")
def admin_logout(response: Response, identity_admin_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if identity_admin_token: db.execute(delete(SystemToken).where(SystemToken.id == token_hash(identity_admin_token))); db.commit()
    response.delete_cookie("identity_admin_token", path="/"); return {"ok": True}


@app.patch("/api/v1/admin/me/password")
def admin_change_password(payload: PasswordUpdate, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    admin.password_hash = ph.hash(payload.password); db.commit(); return {"ok": True}


@app.get("/api/v1/admin/groups")
def admin_groups(admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    groups = db.scalars(select(Group).order_by(Group.created_at))
    return [{"id": x.id, "name": x.name, "is_active": x.is_active, "deleted_at": x.deleted_at, "user_count": db.scalar(select(User).where(User.tenant_id == x.id).count()) if False else len(list(db.scalars(select(User.id).where(User.tenant_id == x.id))))} for x in groups]


@app.post("/api/v1/admin/groups")
def admin_create_group(payload: GroupCreate, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    group = Group(name=payload.name); db.add(group); db.commit(); return {"id": group.id, "name": group.name, "is_active": group.is_active}


@app.patch("/api/v1/admin/groups/{group_id}")
def admin_update_group(group_id: str, payload: GroupUpdate, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group: raise HTTPException(404, "Grupo não encontrado")
    if payload.name is not None: group.name = payload.name
    if payload.is_active is not None:
        group.is_active = payload.is_active
        if not group.is_active: db.execute(delete(AuthToken).where(AuthToken.user_id.in_(select(User.id).where(User.tenant_id == group.id))))
    db.commit(); return {"id": group.id, "name": group.name, "is_active": group.is_active}


@app.get("/api/v1/admin/users")
def admin_users(group_id: str | None = None, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.email)
    if group_id: stmt = stmt.where(User.tenant_id == group_id)
    return [user_dict(x, db) for x in db.scalars(stmt)]


def create_user_record(db: Session, payload: UserCreate, group_id: str):
    if not db.get(Group, group_id): raise HTTPException(404, "Grupo não encontrado")
    email = normalize_email(payload.email)
    if db.scalar(select(User).where(User.email == email)): raise HTTPException(409, "E-mail já cadastrado")
    user = User(tenant_id=group_id, email=email, display_name=payload.display_name, password_hash=ph.hash(payload.password), role=payload.role)
    db.add(user)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "E-mail já cadastrado")
    db.execute(text("INSERT INTO knowledge_base_permissions (id, knowledge_base_id, user_id) SELECT gen_random_uuid()::text, id, :uid FROM knowledge_bases WHERE tenant_id=:gid AND deleted_at IS NULL ON CONFLICT DO NOTHING"), {"uid": user.id, "gid": group_id})
    db.commit(); return user_dict(user, db)


def update_user_record(db: Session, user: User, payload: UserUpdate, allow_group: bool):
    if payload.email is not None:
        email = normalize_email(payload.email)
        duplicate = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if duplicate: raise HTTPException(409, "E-mail já cadastrado")
        user.email = email
    if payload.display_name is not None: user.display_name = payload.display_name
    if payload.password is not None: user.password_hash = ph.hash(payload.password)
    if payload.role is not None: user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not user.is_active: db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
        else: user.deleted_at = None; user.purge_after = None
    if allow_group and payload.group_id is not None:
        if not db.get(Group, payload.group_id): raise HTTPException(404, "Grupo não encontrado")
        if user.tenant_id != payload.group_id:
            user.tenant_id = payload.group_id; user.acl_version += 1
            db.execute(text("DELETE FROM knowledge_base_permissions WHERE user_id=:uid"), {"uid": user.id})
            db.execute(text("INSERT INTO knowledge_base_permissions (id, knowledge_base_id, user_id) SELECT gen_random_uuid()::text, id, :uid FROM knowledge_bases WHERE tenant_id=:gid AND deleted_at IS NULL ON CONFLICT DO NOTHING"), {"uid": user.id, "gid": payload.group_id})
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "E-mail já cadastrado")
    return user_dict(user, db)


@app.post("/api/v1/admin/users")
def admin_create_user(payload: UserCreate, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    if not payload.group_id: raise HTTPException(400, "group_id é obrigatório")
    return create_user_record(db, payload, payload.group_id)


@app.patch("/api/v1/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: UserUpdate, admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "Usuário não encontrado")
    return update_user_record(db, user, payload, allow_group=True)


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(user_id: str, mode: str = "30d", admin: SystemAdmin = Depends(system_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user: raise HTTPException(404, "Usuário não encontrado")
    delete_user_with_mode(db, user, mode); return {"ok": True, "mode": mode}


WEB = Path("/app/web")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.get("/", include_in_schema=False)
def index(): return FileResponse(WEB / "index.html")
