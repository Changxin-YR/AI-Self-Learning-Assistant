from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import os
import re
import uuid
from pathlib import Path

try:
    from celery import Celery
except ImportError:
    Celery = None


if Celery:
    broker_url = os.getenv("REDIS_URL", "").strip()
    if os.getenv("DEV_MODE", "true").lower() != "true" and not broker_url:
        raise RuntimeError("REDIS_URL_REQUIRED")
    celery_app = Celery("study-agent", broker=broker_url or "redis://localhost:6379/0", backend=broker_url or "redis://localhost:6379/0")
    celery_app.conf.task_routes = {
        "app.worker.process_document": {"queue": "documents"},
        "app.worker.process_cleanup_job": {"queue": "cleanup"},
    }
else:
    celery_app = None


def safe_failure_message(error: Exception) -> str:
    code = str(error).split(":", 1)[0].strip()
    return code[:255] if re.fullmatch(r"[A-Z0-9_\-]+", code) else type(error).__name__


def process_document_sync(document_id: int) -> dict[str, str]:
    from app.main import Document, DocumentChunk, ModerationLog, SessionLocal, chunk_text
    from app.parsers import extract_document_text
    from app.providers import get_embedding_provider
    from app.storage import get_storage
    from app.vector_store import get_vector_store
    from app.safety import Risk, get_content_safety_provider

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if not document:
            return {"status": "missing"}
        if document.deleted_at or document.status == "DELETED":
            return {"status": "deleted"}
        document.status = "PARSING"
        document.failure_message = None
        db.commit()
        try:
            raw = get_storage().get(document.storage_key)
            text = extract_document_text(raw, Path(document.filename).suffix.lstrip("."))
            decision = get_content_safety_provider().check_upload_text(text)
            db.add(ModerationLog(user_id=document.user_id, content_type="upload", decision=decision.risk.value, reason=decision.reason, content_hash=__import__("hashlib").sha256(text.encode("utf-8")).hexdigest()))
            db.flush()
            if decision.risk == Risk.BLOCK:
                db.commit()
                raise ValueError("CONTENT_BLOCKED")
            chunks = [chunk for chunk in chunk_text(text) if chunk.strip()]
            if not chunks:
                raise ValueError("DOCUMENT_EMPTY")
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            vector_store = get_vector_store()
            embedding = get_embedding_provider()
            document.status = "EMBEDDING"
            db.commit()
            vectors = asyncio.run(embedding.embed_documents(chunks))
            if len(vectors) != len(chunks) or any(len(vector) != len(vectors[0]) for vector in vectors):
                raise ValueError("EMBEDDING_DIMENSION_INVALID")
            vector_store.ensure_collection(len(vectors[0]))
            # Deterministic point ids make retries idempotent; remove stale points after collection setup.
            vector_store.delete_by_document(document.user_id, document.id)
            for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"study-agent:{document.id}:{index}"))
                db.add(DocumentChunk(user_id=document.user_id, knowledge_base_id=document.knowledge_base_id, document_id=document.id, content=chunk, page_start=1, chunk_index=index, qdrant_point_id=point_id))
                vector_store.upsert(point_id, vector, {"user_id": document.user_id, "knowledge_base_id": document.knowledge_base_id, "document_id": document.id, "chunk_id": index, "page_number": 1})
            document.status = "READY"
            document.failure_message = None
            db.commit()
            return {"status": "READY"}
        except Exception as error:
            db.rollback()
            document = db.get(Document, document_id)
            if document:
                document.status = "FAILED"
                document.failure_message = safe_failure_message(error)
                db.commit()
            raise


CLEANUP_MAX_RETRIES = max(1, int(os.getenv("CLEANUP_MAX_RETRIES", "5")))


def process_cleanup_job_sync(job_id: int) -> dict[str, str | int]:
    """Run a persisted external cleanup intent; every operation is scoped by job.user_id."""
    from app.main import CleanupJob, SessionLocal
    from app.storage import get_storage
    from app.vector_store import get_vector_store

    with SessionLocal() as db:
        job = db.get(CleanupJob, job_id)
        if not job:
            return {"status": "missing"}
        if job.status == "SUCCEEDED":
            return {"status": "SUCCEEDED", "job_id": job.id}
        if job.status == "PROCESSING":
            return {"status": "PROCESSING", "job_id": job.id}
        if job.status == "RETRYING" and job.next_retry_at and job.next_retry_at > datetime.utcnow():
            return {"status": "RETRYING", "job_id": job.id}
        claimed = db.query(CleanupJob).filter(CleanupJob.id == job.id, CleanupJob.status.in_({"PENDING", "RETRYING"})).update({"status": "PROCESSING", "updated_at": datetime.utcnow()}, synchronize_session=False)
        if claimed != 1:
            return {"status": job.status, "job_id": job.id}
        db.refresh(job)
        db.commit()
        try:
            payload = job.payload or {}
            if job.operation == "delete_storage":
                get_storage().delete(str(payload.get("storage_key", "")))
            elif job.operation == "delete_vectors_by_document":
                get_vector_store().delete_by_document(job.user_id, job.resource_id)
            elif job.operation == "delete_vectors_by_kb":
                get_vector_store().delete_by_kb(job.user_id, job.resource_id)
            else:
                raise ValueError("CLEANUP_OPERATION_UNSUPPORTED")
        except Exception as error:
            job.retry_count += 1
            job.last_error = safe_failure_message(error)
            if job.retry_count >= CLEANUP_MAX_RETRIES:
                job.status = "FAILED"
                job.next_retry_at = None
            else:
                job.status = "RETRYING"
                job.next_retry_at = datetime.utcnow() + timedelta(seconds=min(300, 2 ** job.retry_count))
            job.updated_at = datetime.utcnow()
            db.commit()
            return {"status": job.status, "job_id": job.id, "retry_count": job.retry_count}
        job.status = "SUCCEEDED"
        job.last_error = None
        job.next_retry_at = None
        job.updated_at = datetime.utcnow()
        db.commit()
        return {"status": "SUCCEEDED", "job_id": job.id}


if celery_app:
    @celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
    def process_document(self, document_id: int):
        try:
            return process_document_sync(document_id)
        except Exception as error:
            if self.request.retries >= self.max_retries:
                return {"status": "FAILED", "failure_message": safe_failure_message(error)}
            raise self.retry(exc=error, countdown=min(60, 2 ** (self.request.retries + 1)))

    @celery_app.task(bind=True, max_retries=5, soft_time_limit=120, time_limit=180)
    def process_cleanup_job(self, job_id: int):
        try:
            result = process_cleanup_job_sync(job_id)
        except Exception as error:
            if self.request.retries >= self.max_retries:
                return {"status": "FAILED", "job_id": job_id, "last_error": safe_failure_message(error)}
            raise self.retry(exc=error, countdown=min(300, 2 ** (self.request.retries + 1)))
        if result.get("status") == "RETRYING":
            raise self.retry(countdown=min(300, 2 ** int(result.get("retry_count", 1))))
        return result
else:
    class _LocalTask:
        def __init__(self, function):
            self.function = function

        def delay(self, *args, **kwargs):
            return self.function(*args, **kwargs)

        def __call__(self, *args, **kwargs):
            return self.function(*args, **kwargs)

    process_document = _LocalTask(process_document_sync)
    process_cleanup_job = _LocalTask(process_cleanup_job_sync)
