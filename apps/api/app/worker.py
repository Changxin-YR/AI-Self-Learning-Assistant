from __future__ import annotations

import asyncio
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
    celery_app.conf.task_routes = {"app.worker.process_document": {"queue": "documents"}}
else:
    celery_app = None


def safe_failure_message(error: Exception) -> str:
    code = str(error).split(":", 1)[0].strip()
    return code[:255] if re.fullmatch(r"[A-Z0-9_\-]+", code) else type(error).__name__


def process_document_sync(document_id: int) -> dict[str, str]:
    from app.main import Document, DocumentChunk, SessionLocal, chunk_text
    from app.parsers import extract_document_text
    from app.providers import get_embedding_provider
    from app.storage import get_storage
    from app.vector_store import get_vector_store

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


if celery_app:
    @celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
    def process_document(self, document_id: int):
        try:
            return process_document_sync(document_id)
        except Exception as error:
            if self.request.retries >= self.max_retries:
                return {"status": "FAILED", "failure_message": safe_failure_message(error)}
            raise self.retry(exc=error, countdown=min(60, 2 ** (self.request.retries + 1)))
else:
    class _LocalTask:
        def __init__(self, function):
            self.function = function

        def delay(self, *args, **kwargs):
            return self.function(*args, **kwargs)

        def __call__(self, *args, **kwargs):
            return self.function(*args, **kwargs)

    process_document = _LocalTask(process_document_sync)
