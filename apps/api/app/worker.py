import json
import logging
import os
import time
import uuid
from pathlib import Path

import pika
from pypdf import PdfReader

from .config import settings
from .database import SessionLocal
from .integrations import delete_collection, delete_document_points, embed_sync, ensure_collection, upsert_points
from .models import AuditEvent, Document, Job, KnowledgeBase, now

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"worker","message":"%(message)s"}')
log = logging.getLogger("worker")


def extract_text(path: str) -> str:
    source = Path(path)
    if source.suffix.lower() == ".pdf":
        return "\n\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    return source.read_text(encoding="utf-8", errors="replace")


def chunks(text: str, size: int = 1200, overlap: int = 200):
    clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    result = []; start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            split = clean.rfind(" ", start + size // 2, end)
            if split > start: end = split
        piece = clean[start:end].strip()
        if piece: result.append(piece)
        if end >= len(clean): break
        start = max(start + 1, end - overlap)
    return result


def update_job(db, job, status, progress=None, error=None):
    job.status = status; job.updated_at = now()
    if progress is not None: job.progress = progress
    if error is not None: job.error = str(error)[:4000]


def ingest(db, job: Job, payload: dict):
    document = db.get(Document, payload["document_id"]); kb = db.get(KnowledgeBase, payload["knowledge_base_id"])
    if not document or not kb: raise RuntimeError("Documento ou base ausente")
    if document.status == "ready": return
    document.status = "extracting"; update_job(db, job, "running", 10); db.commit()
    text = extract_text(document.path)
    parts = chunks(text)
    if not parts: raise RuntimeError("Documento sem texto extraível")
    document.status = "embedding"; update_job(db, job, "running", 30); db.commit()
    vectors = []
    for offset in range(0, len(parts), 16):
        vectors.extend(embed_sync(parts[offset:offset + 16]))
        update_job(db, job, "running", min(80, 30 + int(50 * len(vectors) / len(parts)))); db.commit()
    ensure_collection(kb.collection_name, len(vectors[0]))
    points = []
    for index, (text, vector) in enumerate(zip(parts, vectors)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document.id}:{index}"))
        points.append({"id": point_id, "vector": vector, "payload": {"document_id": document.id, "filename": document.filename, "chunk": index, "text": text, "tenant_id": kb.tenant_id, "knowledge_base_id": kb.id}})
    for offset in range(0, len(points), 64): upsert_points(kb.collection_name, points[offset:offset + 64])
    document.status = "ready"; document.chunk_count = len(points); kb.version += 1
    update_job(db, job, "completed", 100)
    db.add(AuditEvent(tenant_id=kb.tenant_id, action="document.indexed", target_type="document", target_id=document.id, details={"chunks": len(points)}))


def delete_document(db, job: Job, payload: dict):
    document = db.get(Document, payload["document_id"]); kb = db.get(KnowledgeBase, payload["knowledge_base_id"])
    if not document or not kb: update_job(db, job, "completed", 100); return
    delete_document_points(kb.collection_name, document.id)
    try: Path(document.path).unlink(missing_ok=True)
    except OSError: log.warning("file_delete_failed path=%s", document.path, exc_info=True)
    db.delete(document); kb.version += 1; update_job(db, job, "completed", 100)
    db.add(AuditEvent(tenant_id=kb.tenant_id, action="document.purged", target_type="document", target_id=payload["document_id"]))


def delete_kb(db, job: Job, payload: dict):
    kb = db.get(KnowledgeBase, payload["knowledge_base_id"])
    if not kb: update_job(db, job, "completed", 100); return
    delete_collection(kb.collection_name)
    docs = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
    for document in docs:
        try: Path(document.path).unlink(missing_ok=True)
        except OSError: pass
        db.delete(document)
    update_job(db, job, "completed", 100)
    db.add(AuditEvent(tenant_id=kb.tenant_id, action="knowledge_base.purged", target_type="knowledge_base", target_id=kb.id))


HANDLERS = {"document.ingest": ingest, "document.delete": delete_document, "document.kb_delete": delete_kb}


def callback(channel, method, properties, body):
    payload = json.loads(body); job_id = payload["job_id"]
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.status == "completed": channel.basic_ack(method.delivery_tag); return
        job.attempts += 1; db.commit()
        try:
            handler = HANDLERS.get(method.routing_key)
            if not handler: raise RuntimeError(f"Routing key desconhecida: {method.routing_key}")
            handler(db, job, payload); db.commit(); channel.basic_ack(method.delivery_tag)
        except Exception as exc:
            log.exception("job_failed job_id=%s", job_id)
            job = db.get(Job, job_id); update_job(db, job, "failed" if job.attempts >= 3 else "retrying", error=exc); db.commit()
            channel.basic_reject(method.delivery_tag, requeue=job.attempts < 3)


def run():
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
            channel = connection.channel()
            channel.exchange_declare(exchange="ai.jobs", exchange_type="topic", durable=True)
            channel.exchange_declare(exchange="ai.jobs.dlx", exchange_type="topic", durable=True)
            channel.queue_declare(queue="documents", durable=True, arguments={"x-dead-letter-exchange": "ai.jobs.dlx"})
            channel.queue_declare(queue="documents.dlq", durable=True)
            channel.queue_bind(queue="documents", exchange="ai.jobs", routing_key="document.*")
            channel.queue_bind(queue="documents.dlq", exchange="ai.jobs.dlx", routing_key="#")
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue="documents", on_message_callback=callback)
            log.info("worker_ready")
            channel.start_consuming()
        except KeyboardInterrupt: return
        except Exception:
            log.exception("rabbit_connection_failed"); time.sleep(5)


if __name__ == "__main__": run()
