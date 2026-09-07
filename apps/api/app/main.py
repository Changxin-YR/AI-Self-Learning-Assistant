from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
import jwt
from .providers import get_llm_provider
from .providers import get_embedding_provider
from .parsers import extract_document_text
from .storage import get_storage
from .vector_store import get_vector_store


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'study_agent.db'}")
SECRET = os.getenv("JWT_SECRET", "dev-only-change-me-please-32-chars")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
security = HTTPBearer(auto_error=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str] = mapped_column(String(80), default="学习者")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    openid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(20), default="其他")
    icon: Mapped[str] = mapped_column(String(10), default="📚")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADING")
    failure_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, default=1)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120), default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudyPlan(Base):
    __tablename__ = "study_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    goal: Mapped[str] = mapped_column(String(500), default="")
    target_date: Mapped[date] = mapped_column(Date)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=30)
    weekly_days: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudyTask(Base):
    __tablename__ = "study_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    study_plan_id: Mapped[int] = mapped_column(Integer)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    task_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="TODO")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160), default="知识测验")
    question_count: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question_type: Mapped[str] = mapped_column(String(20), default="SINGLE")
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    correct_answer: Mapped[list[str]] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")
    score_value: Mapped[int] = mapped_column(Integer, default=20)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    answer: Mapped[list[str]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    wrong_count: Mapped[int] = mapped_column(Integer, default=1)


class Mastery(Base):
    __tablename__ = "knowledge_mastery"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(120))
    mastery_score: Mapped[int] = mapped_column(Integer, default=50)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    agent_name: Mapped[str] = mapped_column(String(80), default="study-agent")
    input_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    # Development fallback; production uses the checked-in Alembic migration.
    Base.metadata.create_all(engine)


init_db()


def reset_store() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def db_session():
    with SessionLocal() as db:
        yield db


def token_for(user_id: int) -> str:
    now = datetime.utcnow()
    return jwt.encode({"user_id": user_id, "iat": now, "exp": now + timedelta(seconds=int(os.getenv("JWT_EXPIRE_SECONDS", "7200")))}, SECRET, algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(db_session)) -> User:
    if not credentials:
        raise HTTPException(401, "AUTH_INVALID_TOKEN")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
        user = db.get(User, int(payload["user_id"]))
    except (jwt.InvalidTokenError, KeyError, ValueError):
        user = None
    if not user:
        raise HTTPException(401, "AUTH_INVALID_TOKEN")
    return user


def owned(db: Session, model: Any, item_id: int, user_id: int):
    item = db.scalar(select(model).where(model.id == item_id, model.user_id == user_id))
    if not item:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    return item


class LoginIn(BaseModel):
    nickname: str = "学习者"


class KBIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=500)
    category: str = "其他"
    icon: str = "📚"
    status: str = "ACTIVE"


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    knowledge_base_id: int
    goal: str = ""
    target_date: date
    daily_minutes: int = Field(default=30, ge=10, le=480)
    weekly_days: int = Field(default=5, ge=1, le=7)


class QuizIn(BaseModel):
    knowledge_base_id: int
    question_count: int = Field(default=5, ge=5, le=20)
    question_types: list[str] = Field(default_factory=lambda: ["SINGLE"])


class AnswersIn(BaseModel):
    answers: list[dict[str, Any]]


def kb_json(db: Session, kb: KnowledgeBase) -> dict[str, Any]:
    documents = db.scalars(select(Document).where(Document.knowledge_base_id == kb.id, Document.user_id == kb.user_id)).all()
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb.id, DocumentChunk.user_id == kb.user_id)).all()
    return {"id": kb.id, "name": kb.name, "description": kb.description, "category": kb.category, "icon": kb.icon, "status": kb.status, "document_count": len(documents), "chunk_count": len(chunks), "updated_at": kb.updated_at.isoformat()}


app = FastAPI(title="StudyAgent API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(db_session)):
    db.execute(select(User).limit(1))
    return {"status": "ready", "dependencies": {"database": "ok", "ai": "fake" if DEV_MODE else "configured"}}


@app.post("/api/v1/auth/dev-login")
def dev_login(payload: LoginIn, db: Session = Depends(db_session)):
    if os.getenv("DEV_MODE", str(DEV_MODE)).lower() != "true":
        raise HTTPException(404, "NOT_FOUND")
    nickname = payload.nickname.strip() or "学习者"
    openid = f"dev-{hashlib.sha256(nickname.encode("utf-8")).hexdigest()[:32]}"
    user = db.scalar(select(User).where(User.openid == openid))
    if not user:
        user = User(nickname=nickname, openid=openid)
        db.add(user); db.commit(); db.refresh(user)
    return {"code": 0, "message": "ok", "data": {"access_token": token_for(user.id), "expires_in": 7200, "user": {"id": user.id, "nickname": user.nickname}}}


@app.post("/api/v1/auth/wechat/login")
def wechat_login(payload: dict[str, str], db: Session = Depends(db_session)):
    if os.getenv("DEV_MODE", str(DEV_MODE)).lower() == "true":
        return dev_login(LoginIn(nickname="微信学习者"), db)
    if not os.getenv("WECHAT_APP_ID") or not os.getenv("WECHAT_APP_SECRET"):
        raise HTTPException(503, "WECHAT_PROVIDER_NOT_CONFIGURED")
    code = (payload.get("code") or "").strip()
    if not code: raise HTTPException(400, "WECHAT_CODE_REQUIRED")
    import httpx
    try:
        response = httpx.get("https://api.weixin.qq.com/sns/jscode2session", params={"appid": os.getenv("WECHAT_APP_ID"), "secret": os.getenv("WECHAT_APP_SECRET"), "js_code": code, "grant_type": "authorization_code"}, timeout=8)
        response.raise_for_status(); result = response.json()
    except Exception as error:
        raise HTTPException(503, "WECHAT_PROVIDER_UNAVAILABLE") from error
    if result.get("errcode") or not result.get("openid"): raise HTTPException(400, "WECHAT_LOGIN_FAILED")
    user = db.scalar(select(User).where(User.openid == result["openid"]))
    if not user:
        user = User(openid=result["openid"], nickname="微信学习者"); db.add(user)
    user.created_at = user.created_at or datetime.utcnow(); db.commit(); db.refresh(user)
    return {"code": 0, "message": "ok", "data": {"access_token": token_for(user.id), "expires_in": 7200, "user": {"id": user.id, "nickname": user.nickname}}}


@app.get("/api/v1/auth/profile")
def profile(user: User = Depends(current_user)):
    return {"code": 0, "message": "ok", "data": {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url}}


@app.post("/api/v1/knowledge-bases")
def create_kb(payload: KBIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    kb = KnowledgeBase(user_id=user.id, **payload.model_dump()); db.add(kb); db.commit(); db.refresh(kb)
    return {"code": 0, "message": "ok", "data": kb_json(db, kb)}


@app.get("/api/v1/knowledge-bases")
def list_kbs(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [kb_json(db, kb) for kb in db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user.id, KnowledgeBase.status != "DELETED").order_by(KnowledgeBase.updated_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "page": 1, "page_size": 20, "total": len(items)}}


@app.get("/api/v1/knowledge-bases/{kb_id}")
def get_kb(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {"code": 0, "message": "ok", "data": kb_json(db, owned(db, KnowledgeBase, kb_id, user.id))}


@app.patch("/api/v1/knowledge-bases/{kb_id}")
def update_kb(kb_id: int, payload: KBIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    kb = owned(db, KnowledgeBase, kb_id, user.id); values = payload.model_dump(); [setattr(kb, k, v) for k, v in values.items() if k != "status" or v in {"ACTIVE", "ARCHIVED"}]; db.commit()
    return {"code": 0, "message": "ok", "data": kb_json(db, kb)}


@app.delete("/api/v1/knowledge-bases/{kb_id}")
def delete_kb(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    kb = owned(db, KnowledgeBase, kb_id, user.id); kb.status = "DELETED"; db.commit(); return {"code": 0, "message": "ok", "data": {"deleted": True}}


ALLOWED_EXT = {"pdf", "docx", "pptx", "txt", "md"}


@app.post("/api/v1/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(db_session)):
    kb = owned(db, KnowledgeBase, kb_id, user.id)
    extension = Path(file.filename or "").suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXT:
        raise HTTPException(415, "DOCUMENT_UNSUPPORTED")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "DOCUMENT_TOO_LARGE")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.knowledge_base_id == kb_id, Document.sha256 == digest))
    if existing:
        return {"code": 0, "message": "ok", "data": document_json(existing)}
    document = Document(user_id=user.id, knowledge_base_id=kb_id, filename=Path(file.filename or "document").name, sha256=digest, size_bytes=len(data), status="PARSING")
    db.add(document); db.flush()
    document.storage_key = get_storage().put(user.id, kb_id, document.filename, data)
    if os.getenv("DEV_MODE", str(DEV_MODE)).lower() != "true":
        document.status = "UPLOADED"; db.commit()
        from .worker import process_document
        process_document.delay(document.id)
        return {"code": 0, "message": "ok", "data": document_json(document)}
    text = extract_document_text(data, extension)
    if not text.strip():
        document.status = "FAILED"; document.failure_message = "文件没有可提取文本"; db.commit(); return {"code": 0, "message": "ok", "data": document_json(document)}
    chunks = chunk_text(text)
    vectors = await get_embedding_provider().embed_documents(chunks)
    vector_store = get_vector_store()
    for index, chunk in enumerate(chunks):
        point_id = f"{document.id}-{index}"
        db.add(DocumentChunk(user_id=user.id, knowledge_base_id=kb_id, document_id=document.id, content=chunk, page_start=1, chunk_index=index, qdrant_point_id=point_id))
        vector_store.upsert(point_id, vectors[index], {"user_id": user.id, "knowledge_base_id": kb_id, "document_id": document.id, "chunk_id": index, "page_number": 1})
    document.status = "READY"; db.commit(); db.refresh(document)
    return {"code": 0, "message": "ok", "data": document_json(document)}


def chunk_text(text: str) -> list[str]:
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n{2,}|(?<=[。！？.!?])\s+", text) if p.strip()]
    chunks: list[str] = []; buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) > 1800 and buffer:
            chunks.append(buffer); buffer = buffer[-300:] + " " + paragraph
        else:
            buffer = f"{buffer} {paragraph}".strip()
    if buffer: chunks.append(buffer)
    return chunks or [text[:1800]]


def document_json(document: Document) -> dict[str, Any]:
    return {"id": document.id, "filename": document.filename, "status": document.status, "size_bytes": document.size_bytes, "failure_message": document.failure_message}


@app.get("/api/v1/knowledge-bases/{kb_id}/documents")
def list_documents(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, kb_id, user.id)
    items = [document_json(d) for d in db.scalars(select(Document).where(Document.knowledge_base_id == kb_id, Document.user_id == user.id)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


@app.get("/api/v1/documents/{document_id}/status")
def document_status(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {"code": 0, "message": "ok", "data": document_json(owned(db, Document, document_id, user.id))}


@app.get("/api/v1/documents/{document_id}")
def get_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {"code": 0, "message": "ok", "data": document_json(owned(db, Document, document_id, user.id))}


@app.delete("/api/v1/documents/{document_id}")
def delete_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    document = owned(db, Document, document_id, user.id); db.delete(document); db.commit(); return {"code": 0, "message": "ok", "data": {"deleted": True}}


@app.post("/api/v1/documents/{document_id}/retry")
def retry_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    document = owned(db, Document, document_id, user.id)
    document.status = "PARSING"
    db.commit()
    # DEV_MODE keeps ingestion deterministic and inline; a production worker can
    # replace this branch without changing the API contract.
    document.status = "FAILED" if document.failure_message else "READY"
    db.commit()
    return {"code": 0, "message": "ok", "data": document_json(document)}


class ConversationIn(BaseModel):
    knowledge_base_id: int


@app.post("/api/v1/conversations")
def create_conversation(payload: ConversationIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    conversation = Conversation(user_id=user.id, knowledge_base_id=payload.knowledge_base_id); db.add(conversation); db.commit(); db.refresh(conversation)
    return {"code": 0, "message": "ok", "data": {"id": conversation.id, "title": conversation.title, "knowledge_base_id": conversation.knowledge_base_id}}


@app.get("/api/v1/conversations")
def list_conversations(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [{"id": c.id, "title": c.title, "knowledge_base_id": c.knowledge_base_id} for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.delete("/api/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conversation = owned(db, Conversation, conversation_id, user.id); db.delete(conversation); db.commit(); return {"code": 0, "message": "ok", "data": {"deleted": True}}


@app.get("/api/v1/conversations/{conversation_id}/messages")
def messages(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, Conversation, conversation_id, user.id)
    items = [{"id": m.id, "role": m.role, "content": m.content} for m in db.scalars(select(Message).where(Message.conversation_id == conversation_id, Message.user_id == user.id).order_by(Message.created_at)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.post("/api/v1/conversations/{conversation_id}/messages")
async def chat(conversation_id: int, payload: ChatIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conversation = owned(db, Conversation, conversation_id, user.id)
    db.add(Message(user_id=user.id, conversation_id=conversation_id, role="USER", content=payload.content)); db.flush()
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.user_id == user.id, DocumentChunk.knowledge_base_id == conversation.knowledge_base_id)).all()
    hits = [c for c in chunks if any(word in c.content.lower() for word in re.findall(r"[\w\u4e00-\u9fff]+", payload.content.lower()) if len(word) > 1)]
    result = await get_llm_provider().chat(payload.content, [hit.content for hit in hits])
    answer = result["content"]
    citations = [{"document_id": hits[index].document_id, "page_start": hits[index].page_start, "quote_text": hits[index].content[:120]} for index in result.get("citations", []) if index < len(hits)]
    assistant = Message(user_id=user.id, conversation_id=conversation_id, role="ASSISTANT", content=answer); db.add(assistant); db.commit(); db.refresh(assistant)
    return {"code": 0, "message": "ok", "data": {"id": assistant.id, "content": answer, "citations": citations, "status": "COMPLETED"}}


@app.websocket("/ws/v1/chat/{conversation_id}")
async def chat_stream(websocket: WebSocket, conversation_id: int):
    token = websocket.query_params.get("token", "")
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        user_id = int(payload["user_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        await websocket.close(code=4401); return
    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id))
        if not conversation:
            await websocket.close(code=4404); return
    await websocket.accept()
    try:
        request = await websocket.receive_json()
        await websocket.send_json({"type": "retrieval_started"})
        with SessionLocal() as db:
            chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.user_id == user_id, DocumentChunk.knowledge_base_id == conversation.knowledge_base_id)).all()
        words = re.findall(r"[\w\u4e00-\u9fff]+", str(request.get("content", "")).lower())
        hits = [chunk for chunk in chunks if any(word in chunk.content.lower() for word in words if len(word) > 1)]
        await websocket.send_json({"type": "retrieval_finished", "count": len(hits)})
        result = await get_llm_provider().chat(str(request.get("content", "")), [hit.content for hit in hits])
        await websocket.send_json({"type": "token", "content": result["content"]})
        for index in result.get("citations", []):
            if index < len(hits): await websocket.send_json({"type": "citation", "data": {"document_id": hits[index].document_id, "page_start": hits[index].page_start, "quote_text": hits[index].content[:120]}})
        await websocket.send_json({"type": "done", "message_id": None})
    except WebSocketDisconnect:
        return


@app.post("/api/v1/study-plans")
def create_plan(payload: PlanIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    plan = StudyPlan(user_id=user.id, **payload.model_dump()); db.add(plan); db.commit(); db.refresh(plan)
    return {"code": 0, "message": "ok", "data": plan_json(plan)}


@app.get("/api/v1/study-plans")
def list_plans(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [plan_json(plan) for plan in db.scalars(select(StudyPlan).where(StudyPlan.user_id == user.id).order_by(StudyPlan.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


def plan_json(plan: StudyPlan) -> dict[str, Any]:
    return {"id": plan.id, "name": plan.name, "goal": plan.goal, "knowledge_base_id": plan.knowledge_base_id, "target_date": plan.target_date.isoformat(), "daily_minutes": plan.daily_minutes, "status": plan.status, "progress_percent": plan.progress_percent}


@app.post("/api/v1/study-plans/{plan_id}/activate")
def activate_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    plan = owned(db, StudyPlan, plan_id, user.id); plan.status = "ACTIVE"
    for index, task_type in enumerate(["READ", "LEARN_POINT", "QUIZ", "REVIEW"]):
        db.add(StudyTask(user_id=user.id, study_plan_id=plan.id, knowledge_base_id=plan.knowledge_base_id, task_type=task_type, title=["阅读核心资料", "掌握关键知识点", "完成今日测验", "复习薄弱内容"][index], estimated_minutes=max(10, plan.daily_minutes // 4)))
    db.commit(); return {"code": 0, "message": "ok", "data": plan_json(plan)}


@app.get("/api/v1/tasks/today")
def today_tasks(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [task_json(t) for t in db.scalars(select(StudyTask).where(StudyTask.user_id == user.id)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


def task_json(task: StudyTask) -> dict[str, Any]:
    return {"id": task.id, "title": task.title, "description": task.description, "task_type": task.task_type, "estimated_minutes": task.estimated_minutes, "status": task.status}


@app.post("/api/v1/tasks/{task_id}/complete")
def complete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    task = owned(db, StudyTask, task_id, user.id); task.status = "DONE"; task.completed_at = datetime.utcnow(); db.commit(); return {"code": 0, "message": "ok", "data": task_json(task)}


@app.post("/api/v1/quizzes")
def create_quiz(payload: QuizIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    quiz = Quiz(user_id=user.id, knowledge_base_id=payload.knowledge_base_id, question_count=payload.question_count); db.add(quiz); db.flush()
    supported = {"SINGLE", "MULTIPLE", "TRUE_FALSE", "SHORT"}
    kinds = [item for item in payload.question_types if item in supported] or ["SINGLE"]
    for i in range(payload.question_count):
        kind = kinds[i % len(kinds)]
        if kind == "MULTIPLE":
            options, correct, explanation = ["阅读资料", "完成测验", "忽略错题", "记录复习"], ["A", "B", "D"], "学习闭环需要学习、测验和复习。"
        elif kind == "TRUE_FALSE":
            options, correct, explanation = ["true", "false"], ["true"], "完成任务后应记录学习进度。"
        elif kind == "SHORT":
            options, correct, explanation = [], ["三次握手"], "TCP 使用三次握手建立连接。"
        else:
            options, correct, explanation = ["一次", "三次", "四次", "不确定"], ["B"], "TCP 使用三次握手建立连接。"
        db.add(QuizQuestion(quiz_id=quiz.id, user_id=user.id, question_type=kind, question="TCP 建立连接采用几次握手？" if i == 0 else f"第 {i + 1} 题：以下哪项属于学习闭环？", options=options, correct_answer=correct, explanation=explanation))
    db.commit(); return {"code": 0, "message": "ok", "data": quiz_json(db, quiz, reveal=False)}


def quiz_json(db: Session, quiz: Quiz, reveal: bool) -> dict[str, Any]:
    questions = []
    for q in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.id)).all():
        item = {"id": q.id, "question_type": q.question_type, "question": q.question, "options": q.options, "score_value": q.score_value}
        if reveal: item.update({"correct_answer": q.correct_answer, "explanation": q.explanation})
        questions.append(item)
    return {"id": quiz.id, "title": quiz.title, "status": quiz.status, "question_count": quiz.question_count, "questions": questions}


@app.get("/api/v1/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    quiz = owned(db, Quiz, quiz_id, user.id); return {"code": 0, "message": "ok", "data": quiz_json(db, quiz, reveal=quiz.status == "SUBMITTED")}


@app.post("/api/v1/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: int, payload: AnswersIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    quiz = owned(db, Quiz, quiz_id, user.id)
    if quiz.status == "SUBMITTED": raise HTTPException(409, "QUIZ_ALREADY_SUBMITTED")
    questions = {q.id: q for q in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id, QuizQuestion.user_id == user.id)).all()}
    score = 0
    for answer in payload.answers:
        q = questions.get(int(answer.get("question_id", 0)))
        if not q: continue
        given = sorted(map(str, answer.get("answer", []))); correct = sorted(map(str, q.correct_answer)); is_correct = given == correct
        points = q.score_value if is_correct else 0; score += points
        db.add(QuizAnswer(quiz_id=quiz.id, question_id=q.id, user_id=user.id, answer=given, is_correct=is_correct, score=points))
        if not is_correct: db.add(WrongQuestion(user_id=user.id, question_id=q.id, knowledge_base_id=quiz.knowledge_base_id))
        mastery = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.knowledge_base_id == quiz.knowledge_base_id, Mastery.topic == "TCP 连接管理"))
        if not mastery:
            mastery = Mastery(user_id=user.id, knowledge_base_id=quiz.knowledge_base_id, topic="TCP 连接管理", mastery_score=50); db.add(mastery); db.flush()
        mastery.mastery_score = max(0, min(100, mastery.mastery_score + (6 if is_correct else -8)))
    quiz.status = "SUBMITTED"; quiz.score = score; db.commit()
    return {"code": 0, "message": "ok", "data": {"score": score, "max_score": len(questions) * 20, "correct_rate": round(score / max(1, len(questions) * 20) * 100), "quiz": quiz_json(db, quiz, reveal=True)}}


@app.get("/api/v1/knowledge-bases/{kb_id}/mastery")
def mastery_list(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, kb_id, user.id)
    items = [{"topic": m.topic, "mastery_score": m.mastery_score, "level": "薄弱" if m.mastery_score < 40 else "待加强" if m.mastery_score < 60 else "基本掌握" if m.mastery_score < 80 else "熟练"} for m in db.scalars(select(Mastery).where(Mastery.user_id == user.id, Mastery.knowledge_base_id == kb_id)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.get("/api/v1/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(db_session)):
    tasks = db.scalars(select(StudyTask).where(StudyTask.user_id == user.id)).all(); done = sum(t.status == "DONE" for t in tasks)
    return {"code": 0, "message": "ok", "data": {"today_minutes": done * 15, "task_total": len(tasks), "task_done": done, "weekly_accuracy": 0, "weak_points": ["TCP 连接管理"] if tasks else []}}


@app.get("/api/v1/agent/tools")
def agent_tools(user: User = Depends(current_user)):
    return {"code": 0, "message": "ok", "data": {"allowed": ["get_today_tasks", "complete_study_task", "get_learning_progress", "get_knowledge_base_summary"]}}


class AgentExecuteIn(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/agent/execute")
def agent_execute(payload: AgentExecuteIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if payload.tool_name != "complete_study_task":
        raise HTTPException(400, "AGENT_TOOL_NOT_ALLOWED")
    task_id = int(payload.arguments.get("task_id", 0))
    run = AgentRun(user_id=user.id, input_text=payload.tool_name); db.add(run); db.flush()
    task = owned(db, StudyTask, task_id, user.id)
    task.status = "DONE"; task.completed_at = datetime.utcnow(); db.commit()
    db.add(AgentToolCall(agent_run_id=run.id, user_id=user.id, tool_name=payload.tool_name, arguments_json=payload.arguments, result_summary=f"task:{task.id}")); db.commit()
    return {"code": 0, "message": "ok", "data": {"tool_name": payload.tool_name, "task": task_json(task)}}


@app.get("/api/v1/agent/runs")
def agent_runs(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [{"id": run.id, "agent_name": run.agent_name, "status": run.status, "created_at": run.created_at.isoformat()} for run in db.scalars(select(AgentRun).where(AgentRun.user_id == user.id).order_by(AgentRun.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}
