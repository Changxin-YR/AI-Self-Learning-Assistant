from __future__ import annotations

import os
from pathlib import Path

try:
    from celery import Celery
except ImportError:  # DEV_MODE keeps tests runnable without broker dependencies.
    Celery = None

if Celery:
    celery_app = Celery("study-agent", broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"), backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    celery_app.conf.task_routes = {"app.worker.process_document": {"queue": "documents"}}
else:
    class _LocalTask:
        def delay(self, *args, **kwargs): return None
        def __call__(self, function):
            self.function = function
            return self
    class _LocalCelery:
        def task(self, **kwargs): return _LocalTask()
    celery_app = _LocalCelery()


@celery_app.task(bind=True, max_retries=3, soft_time_limit=300)
def process_document(self, document_id: int):
    from app.main import SessionLocal, Document, DocumentChunk, chunk_text
    from app.parsers import extract_document_text
    from app.storage import get_storage
    from sqlalchemy import select
    try:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if not document: return {"status": "missing"}
            document.status = "PARSING"; db.commit()
            text = extract_document_text(get_storage().get(document.storage_key), Path(document.filename).suffix.lstrip('.'))
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
            for index, chunk in enumerate(chunk_text(text)): db.add(DocumentChunk(user_id=document.user_id, knowledge_base_id=document.knowledge_base_id, document_id=document.id, content=chunk, page_start=1, chunk_index=index))
            document.status = "READY"; db.commit(); return {"status": "READY"}
    except Exception as error:
        raise self.retry(exc=error, countdown=10)
