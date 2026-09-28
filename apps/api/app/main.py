import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, SessionLocal, engine
from .integrations import cache_client, cache_key, embed_async, publish_job, search_collection
from .models import (
    AppSetting, AuditEvent, Conversation, Document, Job, KnowledgeBase,
    KnowledgeBasePermission, Message, Tenant, User, now,
)
from .security import current_user, get_db, lab_admin
from .telemetry import configure

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}')
log = logging.getLogger("ai-harness")
CHAT_REQUESTS = Counter("chat_requests_total", "Total de requisições de chat", ["status"])
CHAT_DURATION = Histogram("chat_duration_seconds", "Duração do chat")
CACHE_EVENTS = Counter("cache_events_total", "Eventos do cache", ["kind", "result"])

app = FastAPI(title="AI RAG Harness", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
configure(app)


def bootstrap():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.get(AppSetting, "retention"):
            db.add(AppSetting(key="retention", value={"default_days": settings.retention_days}))
        db.commit()


@app.on_event("startup")
def startup():
    os.makedirs(settings.upload_dir, exist_ok=True)
    bootstrap()


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", secrets.token_hex(8))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_error request_id=%s path=%s", request_id, request.url.path)
        raise
    response.headers["x-request-id"] = request_id
    response.headers["x-content-type-options"] = "nosniff"
    log.info("request request_id=%s method=%s path=%s status=%s duration_ms=%.1f", request_id, request.method, request.url.path, response.status_code, (time.perf_counter() - started) * 1000)
    return response


class SessionCreate(BaseModel):
    title: str = "Nova conversa"


class SessionUpdate(BaseModel):
    title: str | None = None
    selected_kb_ids: list[str] | None = None
    is_archived: bool | None = None


class KBCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    tenant_id: str | None = None


class KBUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    status: Literal["active", "disabled"] | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=16000)
    knowledge_base_ids: list[str] = []
    temperature: float = Field(default=0.2, ge=0, le=1.5)
    bypass_cache: bool = False


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    retention_days: int | None = Field(default=None, ge=0, le=365)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    retention_days: int | None = Field(default=None, ge=0, le=365)


class RetentionUpdate(BaseModel):
    default_days: Literal[0, 7, 15, 30, 60, 90]


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    tenant_id: str
    role: Literal["admin", "client"] = "client"


def audit(db: Session, user: User | None, action: str, target_type: str | None = None, target_id: str | None = None, details: dict | None = None):
    db.add(AuditEvent(tenant_id=user.tenant_id if user else None, user_id=user.id if user else None, action=action, target_type=target_type, target_id=target_id, details=details or {}))


def session_dict(item: Conversation):
    return {
        "id": item.id, "title": item.title, "selected_kb_ids": item.selected_kb_ids,
        "is_pinned": item.is_pinned, "is_archived": item.is_archived,
        "deleted_at": item.deleted_at, "purge_after": item.purge_after,
        "created_at": item.created_at, "updated_at": item.updated_at,
    }


def get_owned_session(db: Session, user: User, session_id: str, include_deleted: bool = False):
    item = db.get(Conversation, session_id)
    if not item or item.user_id != user.id or (item.deleted_at and not include_deleted):
        raise HTTPException(404, "Conversa não encontrada")
    return item


def allowed_kbs(db: Session, user: User, ids: list[str] | None = None, active_only: bool = True):
    stmt = select(KnowledgeBase).where(KnowledgeBase.tenant_id == user.tenant_id, KnowledgeBase.deleted_at.is_(None))
    if ids is not None:
        stmt = stmt.where(KnowledgeBase.id.in_(ids))
    if active_only:
        stmt = stmt.where(KnowledgeBase.status == "active")
    bases = list(db.scalars(stmt))
    if user.role in {"admin", "lab_admin"}:
        return bases
    permitted = set(db.scalars(select(KnowledgeBasePermission.knowledge_base_id).where(KnowledgeBasePermission.user_id == user.id)))
    return [kb for kb in bases if kb.id in permitted]


def admin_kb(db: Session, user: User, kb_id: str, include_deleted: bool = False):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb or kb.tenant_id != user.tenant_id or (kb.deleted_at and not include_deleted):
        raise HTTPException(404, "Base não encontrada")
    return kb


@app.get("/health")
def health():
    return {"status": "ok", "service": "api"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": "admin" if user.role in {"admin", "lab_admin"} else "client", "tenant_id": user.tenant_id}


@app.get("/api/v1/sessions")
def list_sessions(scope: str = "active", q: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if scope == "trash":
        stmt = stmt.where(Conversation.deleted_at.is_not(None))
    else:
        stmt = stmt.where(Conversation.deleted_at.is_(None))
        if scope == "archived":
            stmt = stmt.where(Conversation.is_archived.is_(True))
        elif scope == "active":
            stmt = stmt.where(Conversation.is_archived.is_(False))
    if q:
        stmt = stmt.where(Conversation.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Conversation.is_pinned.desc(), Conversation.pinned_at.desc().nullslast(), Conversation.updated_at.desc())
    return [session_dict(x) for x in db.scalars(stmt)]


@app.post("/api/v1/sessions")
def create_session(payload: SessionCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = Conversation(tenant_id=user.tenant_id, user_id=user.id, title=payload.title[:200])
    db.add(item); db.flush(); audit(db, user, "session.create", "session", item.id); db.commit()
    return session_dict(item)


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id, True)
    messages = list(db.scalars(select(Message).where(Message.conversation_id == item.id).order_by(Message.created_at)))
    return {**session_dict(item), "messages": [{"id": m.id, "role": m.role, "content": m.content, "sources": m.sources, "technical": m.technical, "created_at": m.created_at} for m in messages]}


@app.patch("/api/v1/sessions/{session_id}")
def update_session(session_id: str, payload: SessionUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id)
    if payload.title is not None: item.title = payload.title[:200]
    if payload.is_archived is not None: item.is_archived = payload.is_archived
    if payload.selected_kb_ids is not None:
        permitted = {x.id for x in allowed_kbs(db, user, payload.selected_kb_ids)}
        if permitted != set(payload.selected_kb_ids): raise HTTPException(403, "Uma ou mais bases não estão disponíveis")
        item.selected_kb_ids = payload.selected_kb_ids
    item.updated_at = now(); audit(db, user, "session.update", "session", item.id); db.commit()
    return session_dict(item)


@app.patch("/api/v1/sessions/{session_id}/pin")
def pin_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id); item.is_pinned = True; item.pinned_at = now(); db.commit(); return session_dict(item)


@app.patch("/api/v1/sessions/{session_id}/unpin")
def unpin_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id); item.is_pinned = False; item.pinned_at = None; db.commit(); return session_dict(item)


@app.delete("/api/v1/sessions/{session_id}")
def trash_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id)
    setting = db.get(AppSetting, "retention")
    days = (db.get(Tenant, user.tenant_id).retention_days if db.get(Tenant, user.tenant_id) else None)
    days = days if days is not None else int((setting.value if setting else {}).get("default_days", 30))
    if days == 0:
        item_id = item.id
        audit(db, user, "session.purge_immediate", "session", item_id, {"retention_days": 0})
        db.execute(delete(Message).where(Message.conversation_id == item_id)); db.delete(item); db.commit()
        return {"id": item_id, "purged": True}
    item.deleted_at = now(); item.purge_after = now() + timedelta(days=days)
    audit(db, user, "session.trash", "session", item.id, {"retention_days": days}); db.commit()
    return session_dict(item)


@app.post("/api/v1/sessions/{session_id}/restore")
def restore_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id, True); item.deleted_at = None; item.purge_after = None; audit(db, user, "session.restore", "session", item.id); db.commit(); return session_dict(item)


@app.delete("/api/v1/sessions/{session_id}/purge")
def purge_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = get_owned_session(db, user, session_id, True)
    audit(db, user, "session.purge", "session", item.id)
    db.execute(delete(Message).where(Message.conversation_id == item.id)); db.delete(item); db.commit()
    return {"ok": True}


@app.get("/api/v1/knowledge-bases")
def list_kbs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role in {"admin", "lab_admin"}:
        bases = list(db.scalars(select(KnowledgeBase).where(KnowledgeBase.tenant_id == user.tenant_id, KnowledgeBase.deleted_at.is_(None)).order_by(KnowledgeBase.created_at.desc())))
    else:
        bases = allowed_kbs(db, user, active_only=True)
    tenants = {x.id: x.name for x in db.scalars(select(Tenant))}
    return [{"id": x.id, "tenant_id": x.tenant_id, "tenant_name": tenants.get(x.tenant_id), "name": x.name, "status": x.status, "version": x.version, "embedding_model": x.embedding_model, "created_at": x.created_at} for x in bases]


@app.post("/api/v1/knowledge-bases")
def create_kb(payload: KBCreate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    tenant_id = user.tenant_id
    if payload.tenant_id and payload.tenant_id != tenant_id: raise HTTPException(403, "Não é permitido criar bases em outro grupo")
    item = KnowledgeBase(tenant_id=tenant_id, name=payload.name, collection_name=f"kb_{tenant_id.replace('-', '')}_{secrets.token_hex(6)}", embedding_model=settings.embed_model)
    db.add(item); db.flush()
    for tenant_user in db.scalars(select(User).where(User.tenant_id == tenant_id, User.is_active.is_(True), User.deleted_at.is_(None))):
        db.add(KnowledgeBasePermission(knowledge_base_id=item.id, user_id=tenant_user.id))
    audit(db, user, "knowledge_base.create", "knowledge_base", item.id, {"tenant_id": tenant_id}); db.commit()
    return {"id": item.id, "name": item.name, "status": item.status, "version": item.version}


@app.patch("/api/v1/knowledge-bases/{kb_id}")
def update_kb(kb_id: str, payload: KBUpdate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    item = admin_kb(db, user, kb_id)
    if payload.name is not None: item.name = payload.name
    if payload.status is not None: item.status = payload.status
    item.version += 1; audit(db, user, "knowledge_base.update", "knowledge_base", item.id, payload.model_dump(exclude_none=True)); db.commit()
    return {"id": item.id, "name": item.name, "status": item.status, "version": item.version}


@app.delete("/api/v1/knowledge-bases/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    item = admin_kb(db, user, kb_id)
    item.status = "deleting"; item.deleted_at = now(); item.version += 1
    job = Job(tenant_id=item.tenant_id, kind="knowledge_base.delete", payload={"knowledge_base_id": item.id})
    db.add(job); db.flush(); audit(db, user, "knowledge_base.delete_requested", "knowledge_base", item.id); db.commit()
    publish_job("document.kb_delete", {"job_id": job.id, "knowledge_base_id": item.id})
    return {"job_id": job.id, "status": "queued"}


@app.get("/api/v1/knowledge-bases/{kb_id}/documents")
def list_documents(kb_id: str, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    kb = admin_kb(db, user, kb_id)
    docs = db.scalars(select(Document).where(Document.knowledge_base_id == kb_id).order_by(Document.created_at.desc()))
    return [{"id": x.id, "filename": x.filename, "status": x.status, "chunk_count": x.chunk_count, "error": x.error, "created_at": x.created_at} for x in docs]


@app.post("/api/v1/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    kb = admin_kb(db, user, kb_id)
    suffix = Path(file.filename or "file.txt").suffix.lower()
    if suffix not in {".txt", ".md", ".pdf"}: raise HTTPException(415, "Use PDF, TXT ou MD")
    data = await file.read(settings.upload_max_mb * 1024 * 1024 + 1)
    if len(data) > settings.upload_max_mb * 1024 * 1024: raise HTTPException(413, "Arquivo excede o limite")
    digest = hashlib.sha256(data).hexdigest()
    directory = Path(settings.upload_dir) / kb.tenant_id / kb.id; directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(file.filename or "document").name)
    document = Document(knowledge_base_id=kb.id, filename=safe_name, path="", sha256=digest)
    db.add(document); db.flush()
    path = directory / f"{document.id}_{safe_name}"; path.write_bytes(data); document.path = str(path)
    job = Job(tenant_id=kb.tenant_id, kind="document.ingest", payload={"document_id": document.id, "knowledge_base_id": kb.id})
    db.add(job); db.flush(); audit(db, user, "document.upload", "document", document.id, {"filename": safe_name}); db.commit()
    publish_job("document.ingest", {"job_id": job.id, "document_id": document.id, "knowledge_base_id": kb.id})
    return {"document_id": document.id, "job_id": job.id, "status": "queued"}


@app.delete("/api/v1/documents/{document_id}")
def remove_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    document = db.get(Document, document_id); kb = db.get(KnowledgeBase, document.knowledge_base_id) if document else None
    if not document or not kb or kb.tenant_id != user.tenant_id: raise HTTPException(404, "Documento não encontrado")
    document.status = "deleting"
    job = Job(tenant_id=kb.tenant_id, kind="document.delete", payload={"document_id": document.id, "knowledge_base_id": kb.id})
    db.add(job); db.flush(); audit(db, user, "document.delete_requested", "document", document.id); db.commit()
    publish_job("document.delete", {"job_id": job.id, "document_id": document.id, "knowledge_base_id": kb.id})
    return {"job_id": job.id, "status": "queued"}


@app.get("/api/v1/jobs")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    jobs = db.scalars(select(Job).where(Job.tenant_id == user.tenant_id).order_by(Job.created_at.desc()).limit(100))
    return [{"id": x.id, "kind": x.kind, "status": x.status, "progress": x.progress, "error": x.error, "attempts": x.attempts, "created_at": x.created_at} for x in jobs]


@app.get("/api/v1/audit")
def list_audit(db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    events = db.scalars(select(AuditEvent).where(AuditEvent.tenant_id == user.tenant_id).order_by(AuditEvent.created_at.desc()).limit(200))
    return [{"id": x.id, "action": x.action, "target_type": x.target_type, "target_id": x.target_id, "details": x.details, "created_at": x.created_at} for x in events]


@app.get("/api/v1/tenants")
def list_tenants(db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    x = db.get(Tenant, user.tenant_id)
    return [{"id": x.id, "name": x.name, "retention_days": x.retention_days, "created_at": x.created_at}]


@app.post("/api/v1/tenants")
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    raise HTTPException(403, "Grupos são criados no Identity Manager")


@app.patch("/api/v1/tenants/{tenant_id}")
def update_tenant(tenant_id: str, payload: TenantUpdate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    if tenant_id != user.tenant_id: raise HTTPException(403, "Grupo fora do escopo")
    item = db.get(Tenant, tenant_id)
    if not item: raise HTTPException(404, "Cliente não encontrado")
    fields = payload.model_fields_set
    if "name" in fields: item.name = payload.name
    if "retention_days" in fields: item.retention_days = payload.retention_days
    audit(db, user, "tenant.update", "tenant", item.id, payload.model_dump(exclude_unset=True)); db.commit()
    return {"id": item.id, "name": item.name, "retention_days": item.retention_days}


@app.get("/api/v1/settings/retention")
def get_retention(db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    setting = db.get(AppSetting, "retention")
    tenant = db.get(Tenant, user.tenant_id)
    default = int((setting.value if setting else {}).get("default_days", settings.retention_days))
    return {"default_days": tenant.retention_days if tenant and tenant.retention_days is not None else default, "inherited_default_days": default}


@app.patch("/api/v1/settings/retention")
def update_retention(payload: RetentionUpdate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    tenant = db.get(Tenant, user.tenant_id); tenant.retention_days = payload.default_days
    audit(db, user, "settings.retention_update", "tenant", tenant.id, {"default_days": payload.default_days}); db.commit()
    return {"default_days": payload.default_days}


@app.get("/api/v1/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    return [{"id": x.id, "email": x.email, "display_name": x.display_name, "role": "admin" if x.role in {"admin", "lab_admin"} else "client", "tenant_id": x.tenant_id, "is_active": x.is_active} for x in db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.email))]


@app.post("/api/v1/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(lab_admin)):
    raise HTTPException(410, "Use o serviço Identity Manager para criar usuários")


@app.put("/api/v1/knowledge-bases/{kb_id}/permissions/{user_id}")
def grant_kb(kb_id: str, user_id: str, db: Session = Depends(get_db), admin: User = Depends(lab_admin)):
    kb, target = db.get(KnowledgeBase, kb_id), db.get(User, user_id)
    if not kb or not target or kb.tenant_id != admin.tenant_id or target.tenant_id != admin.tenant_id: raise HTTPException(400, "Base e usuário devem pertencer ao seu grupo")
    existing = db.scalar(select(KnowledgeBasePermission).where(KnowledgeBasePermission.knowledge_base_id == kb_id, KnowledgeBasePermission.user_id == user_id))
    if not existing: db.add(KnowledgeBasePermission(knowledge_base_id=kb_id, user_id=user_id))
    target.acl_version += 1; audit(db, admin, "knowledge_base.permission_grant", "knowledge_base", kb_id, {"user_id": user_id}); db.commit(); return {"ok": True}


@app.get("/api/v1/knowledge-bases/{kb_id}/permissions")
def list_kb_permissions(kb_id: str, db: Session = Depends(get_db), admin: User = Depends(lab_admin)):
    kb = admin_kb(db, admin, kb_id)
    granted = set(db.scalars(select(KnowledgeBasePermission.user_id).where(KnowledgeBasePermission.knowledge_base_id == kb_id)))
    users = db.scalars(select(User).where(User.tenant_id == kb.tenant_id, User.deleted_at.is_(None)).order_by(User.email))
    return [{"id": x.id, "email": x.email, "role": x.role, "granted": x.id in granted} for x in users]


@app.delete("/api/v1/knowledge-bases/{kb_id}/permissions/{user_id}")
def revoke_kb(kb_id: str, user_id: str, db: Session = Depends(get_db), admin: User = Depends(lab_admin)):
    kb, target = db.get(KnowledgeBase, kb_id), db.get(User, user_id)
    if not kb or not target or kb.tenant_id != admin.tenant_id or target.tenant_id != admin.tenant_id: raise HTTPException(404, "Base ou usuário não encontrado")
    db.execute(delete(KnowledgeBasePermission).where(KnowledgeBasePermission.knowledge_base_id == kb_id, KnowledgeBasePermission.user_id == user_id))
    if target: target.acl_version += 1
    audit(db, admin, "knowledge_base.permission_revoke", "knowledge_base", kb_id, {"user_id": user_id}); db.commit(); return {"ok": True}


@app.post("/api/v1/cache/clear")
def clear_cache(user: User = Depends(lab_admin)):
    try: cache_client().flushdb()
    except Exception as exc: raise HTTPException(503, f"Cache indisponível: {exc}")
    return {"ok": True}


@app.get("/api/v1/cache/status")
def cache_status(user: User = Depends(lab_admin)):
    info = cache_client().info("memory")
    return {"used_memory": info.get("used_memory"), "used_memory_human": info.get("used_memory_human"), "maxmemory": info.get("maxmemory")}


def guardrail(text: str):
    lowered = text.lower()
    patterns = ["ignore todas as instruções", "revele o prompt do sistema", "system prompt", "senha:", "api_key="]
    hits = [p for p in patterns if p in lowered]
    return {"allowed": not hits, "hits": hits, "mode": "enforce"}


@app.post("/api/v1/chat/stream")
async def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    started = time.perf_counter(); conversation = get_owned_session(db, user, payload.session_id)
    decision = guardrail(payload.message)
    if not decision["allowed"]:
        audit(db, user, "guardrail.block", "session", conversation.id, decision); db.commit(); CHAT_REQUESTS.labels("blocked").inc()
        raise HTTPException(400, {"code": "GUARDRAIL_BLOCK", "details": decision})
    requested_ids = payload.knowledge_base_ids or conversation.selected_kb_ids
    bases = allowed_kbs(db, user, requested_ids)
    if set(requested_ids) != {x.id for x in bases}: raise HTTPException(403, "Uma base está desativada ou não autorizada")
    user_message = Message(conversation_id=conversation.id, role="user", content=payload.message, technical={"guardrail": decision})
    db.add(user_message); conversation.selected_kb_ids = requested_ids; conversation.updated_at = now()
    if conversation.title == "Nova conversa": conversation.title = payload.message[:80]
    db.commit()

    sources = []; retrieval_ms = 0.0; cache_result = "bypass"
    if bases:
        retrieval_start = time.perf_counter()
        rkey = cache_key("rag", {"tenant": user.tenant_id, "user": user.id, "acl": user.acl_version, "bases": [(x.id, x.version) for x in bases], "q": payload.message})
        cached = None
        if not payload.bypass_cache:
            try: cached = cache_client().get(rkey)
            except Exception: cached = None
        if cached:
            sources = json.loads(cached); cache_result = "hit"; CACHE_EVENTS.labels("rag", "hit").inc()
        else:
            vector = await embed_async(payload.message)
            for kb in bases:
                for point in await search_collection(kb.collection_name, vector, 4):
                    p = point.get("payload", {})
                    sources.append({"knowledge_base_id": kb.id, "knowledge_base": kb.name, "document_id": p.get("document_id"), "filename": p.get("filename"), "chunk": p.get("chunk"), "text": p.get("text", ""), "score": point.get("score", 0)})
            sources = sorted(sources, key=lambda x: x["score"], reverse=True)[:6]
            try: cache_client().setex(rkey, 600, json.dumps(sources, ensure_ascii=False))
            except Exception: pass
            cache_result = "miss"; CACHE_EVENTS.labels("rag", "miss").inc()
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    history = list(db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.desc()).limit(12)))[::-1]
    context = "\n\n".join(f"[Fonte {i+1}: {s['knowledge_base']} / {s['filename']}]\n{s['text']}" for i, s in enumerate(sources))
    system = "Você é um assistente em português do Brasil. Seja claro e honesto. Quando houver fontes, responda somente com apoio nelas e cite [Fonte N]. Se não houver evidência, diga que não encontrou na base."
    if context: system += "\n\nCONTEXTO RAG:\n" + context
    ollama_messages = [{"role": "system", "content": system}] + [{"role": m.role, "content": m.content} for m in history]
    technical = {"model": settings.chat_model, "context_limit": settings.context_tokens, "selected_bases": [x.name for x in bases], "retrieval_ms": round(retrieval_ms, 2), "rag_cache": cache_result, "guardrail": decision, "sources_count": len(sources), "prompt_estimated_tokens": sum(len(x["content"]) for x in ollama_messages) // 4}

    async def stream():
        answer = ""; first_token_ms = None
        yield f"event: metadata\ndata: {json.dumps({'sources': sources, 'technical': technical}, ensure_ascii=False)}\n\n"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{settings.ollama_url}/api/chat", json={"model": settings.chat_model, "messages": ollama_messages, "stream": True, "options": {"temperature": payload.temperature, "num_ctx": settings.context_tokens}, "keep_alive": "10m"}) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line: continue
                        item = json.loads(line); token = item.get("message", {}).get("content", "")
                        if token:
                            if first_token_ms is None: first_token_ms = round((time.perf_counter() - started) * 1000, 2)
                            answer += token
                            yield f"event: token\ndata: {json.dumps({'text': token}, ensure_ascii=False)}\n\n"
            duration = round((time.perf_counter() - started) * 1000, 2)
            technical.update({"first_token_ms": first_token_ms, "total_ms": duration, "answer_estimated_tokens": len(answer) // 4})
            with SessionLocal() as save_db:
                save_db.add(Message(conversation_id=conversation.id, role="assistant", content=answer, sources=sources, technical=technical)); save_db.commit()
            CHAT_REQUESTS.labels("ok").inc(); CHAT_DURATION.observe(duration / 1000)
            yield f"event: done\ndata: {json.dumps({'technical': technical}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            log.exception("chat_stream_error")
            CHAT_REQUESTS.labels("error").inc()
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/v1/system/services")
async def service_status():
    targets = {
        "api": "http://localhost:8000/health", "frontend": "http://frontend:8080/health",
        "identity": "http://identity:8010/health", "access-portal": "http://access-portal:8083/health", "service-map": "http://service-map:8081/health", "ollama": f"{settings.ollama_url}/api/tags",
        "qdrant": f"{settings.qdrant_url}/healthz", "prometheus": "http://prometheus:9090/-/healthy",
        "loki": "http://loki:3100/metrics", "tempo": "http://tempo:3200/metrics", "grafana": "http://grafana:3000/api/health",
        "otel-collector": "http://otel-collector:13133/",
    }
    result = []
    async with httpx.AsyncClient(timeout=2) as client:
        for name, url in targets.items():
            before = time.perf_counter()
            try:
                response = await client.get(url); state = "healthy" if response.status_code < 400 else "degraded"
                detail = f"HTTP {response.status_code}"
            except Exception as exc: state, detail = "unhealthy", type(exc).__name__
            result.append({"name": name, "status": state, "latency_ms": round((time.perf_counter() - before) * 1000, 1), "detail": detail})
    for name, check in (("postgres", lambda: engine.connect().close()), ("valkey", lambda: cache_client().ping())):
        before = time.perf_counter()
        try: check(); state, detail = "healthy", "connected"
        except Exception as exc: state, detail = "unhealthy", type(exc).__name__
        result.append({"name": name, "status": state, "latency_ms": round((time.perf_counter() - before) * 1000, 1), "detail": detail})
    rabbit = urlparse(settings.rabbitmq_url)
    auth = (unquote(rabbit.username or ""), unquote(rabbit.password or ""))
    before = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            overview, queue = await client.get("http://rabbitmq:15672/api/overview", auth=auth), await client.get("http://rabbitmq:15672/api/queues/%2F/documents", auth=auth)
        overview.raise_for_status(); queue.raise_for_status(); queue_data = queue.json()
        result.append({"name": "rabbitmq", "status": "healthy", "latency_ms": round((time.perf_counter() - before) * 1000, 1), "detail": f"fila={queue_data.get('messages', 0)}"})
        consumers = int(queue_data.get("consumers", 0))
        result.append({"name": "worker", "status": "healthy" if consumers else "unhealthy", "latency_ms": 0, "detail": f"consumidores={consumers}"})
    except Exception as exc:
        result.append({"name": "rabbitmq", "status": "unhealthy", "latency_ms": round((time.perf_counter() - before) * 1000, 1), "detail": type(exc).__name__})
        result.append({"name": "worker", "status": "unhealthy", "latency_ms": 0, "detail": "broker indisponível"})
    try:
        heartbeat = cache_client().get("heartbeat:maintenance")
        result.append({"name": "maintenance-worker", "status": "healthy" if heartbeat else "unhealthy", "latency_ms": 0, "detail": "heartbeat ativo" if heartbeat else "heartbeat expirado"})
    except Exception as exc:
        result.append({"name": "maintenance-worker", "status": "unhealthy", "latency_ms": 0, "detail": type(exc).__name__})
    return {"services": result, "relations": [["frontend", "identity"], ["frontend", "access-portal"], ["identity", "postgres"], ["frontend", "api"], ["api", "ollama"], ["api", "postgres"], ["api", "qdrant"], ["api", "valkey"], ["api", "rabbitmq"], ["rabbitmq", "worker"], ["api", "otel-collector"], ["otel-collector", "tempo"], ["prometheus", "grafana"], ["loki", "grafana"], ["tempo", "grafana"]]}
