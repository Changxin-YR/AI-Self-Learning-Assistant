from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, select, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
import jwt
from .providers import dev_mode, get_embedding_provider, get_llm_provider, probe_provider_config, validate_provider_config
from .storage import get_storage
from .vector_store import get_vector_store


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'study_agent.db'}")
SECRET = os.getenv("JWT_SECRET", "dev-only-change-me-please-32-chars")
DEV_MODE = dev_mode()
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
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
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
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    extension: Mapped[str] = mapped_column(String(10), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADING")
    failure_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120), default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
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
    foundation_level: Mapped[str] = mapped_column(String(20), default="一般")
    intensity: Mapped[str] = mapped_column(String(20), default="标准")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    generated_schedule: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StudyTask(Base):
    __tablename__ = "study_tasks"
    __table_args__ = (UniqueConstraint("study_plan_id", "scheduled_date", name="uq_study_tasks_plan_date_constraint"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    study_plan_id: Mapped[int] = mapped_column(Integer)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    task_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500), default="")
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    status: Mapped[str] = mapped_column(String(20), default="TODO")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160), default="知识测验")
    question_count: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    scoring_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[str] = mapped_column(Text, default="")
    source_chunk_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    score_value: Mapped[int] = mapped_column(Integer, default=20)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("quiz_id", "question_id", "user_id", name="uq_quiz_answers_question_constraint"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    answer: Mapped[list[str]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    score: Mapped[int] = mapped_column(Integer, default=0)
    ai_feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    wrong_count: Mapped[int] = mapped_column(Integer, default=1)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    mastered: Mapped[bool] = mapped_column(Boolean, default=False)


class Mastery(Base):
    __tablename__ = "knowledge_mastery"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(String(120))
    mastery_score: Mapped[int] = mapped_column(Integer, default=50)
    confidence: Mapped[int] = mapped_column(Integer, default=20)
    quiz_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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


class UserMemory(Base):
    __tablename__ = "user_memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    memory_type: Mapped[str] = mapped_column(String(40))
    memory_key: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(80), default="user")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def is_dev() -> bool:
    return os.getenv("DEV_MODE", str(DEV_MODE)).lower() == "true"


def validate_security_config() -> None:
    secret = os.getenv("JWT_SECRET", SECRET)
    weak_values = {"dev-only-change-me-please-32-chars", "change-me", "changeme", "secret", "password"}
    if not is_dev() and (secret.lower() in weak_values or len(secret) < 32 or len(set(secret)) < 8):
        raise RuntimeError("JWT_SECRET_WEAK")


def init_db() -> None:
    # Development convenience only. Production schema is managed by Alembic.
    if is_dev():
        Base.metadata.create_all(engine)


init_db()


def reset_store() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        from . import vector_store
        vector_store._store = None
    except Exception:
        pass
    _rate_limits.clear()


def db_session():
    with SessionLocal() as db:
        yield db


def token_for(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"user_id": user_id, "iat": now, "exp": now + timedelta(seconds=token_expire_seconds())}, os.getenv("JWT_SECRET", SECRET), algorithm="HS256")


def token_expire_seconds() -> int:
    try:
        return max(1, int(os.getenv("JWT_EXPIRE_SECONDS", "7200")))
    except ValueError as error:
        raise RuntimeError("JWT_EXPIRE_SECONDS_INVALID") from error


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(db_session)) -> User:
    validate_security_config()
    if not credentials:
        raise HTTPException(401, "AUTH_INVALID_TOKEN")
    try:
        payload = jwt.decode(credentials.credentials, os.getenv("JWT_SECRET", SECRET), algorithms=["HS256"])
        user = db.get(User, int(payload["user_id"]))
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        user = None
    if not user or user.status != "ACTIVE":
        raise HTTPException(401, "AUTH_INVALID_TOKEN")
    return user


def owned(db: Session, model: Any, item_id: int, user_id: int):
    criteria = [model.id == item_id, model.user_id == user_id]
    if hasattr(model, "deleted_at"):
        criteria.append(model.deleted_at.is_(None))
    item = db.scalar(select(model).where(*criteria))
    if not item or getattr(item, "status", None) == "DELETED":
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
    foundation_level: str = "一般"
    intensity: str = "标准"
    timezone: str = "Asia/Shanghai"


class GeneratedPlanTask(BaseModel):
    type: str = "LEARN_POINT"
    title: str = Field(min_length=1, max_length=200)
    estimated_minutes: int = Field(default=30, ge=5, le=480)


class GeneratedPlanDay(BaseModel):
    date: str = ""
    goal: str = Field(default="", max_length=500)
    estimated_minutes: int = Field(default=30, ge=5, le=480)
    tasks: list[GeneratedPlanTask] = Field(default_factory=list)


class GeneratedPlan(BaseModel):
    plan_name: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=1000)
    days: list[GeneratedPlanDay] = Field(default_factory=list, max_length=366)


class QuizIn(BaseModel):
    knowledge_base_id: int
    question_count: int = Field(default=5, ge=5, le=20)
    question_types: list[str] = Field(default_factory=lambda: ["SINGLE"])
    source_type: str = "knowledge_base"
    study_task_id: int | None = None
    difficulty: str = "medium"


class GeneratedQuestion(BaseModel):
    question_type: str = "SINGLE"
    question: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list)
    correct_answer: list[str] = Field(default_factory=list)
    explanation: str = ""
    reference_answer: str = ""
    scoring_points: list[str] = Field(default_factory=list)
    evidence: str = ""
    source_chunk_ids: list[int] = Field(default_factory=list)
    difficulty: str = "medium"


class ShortAnswerScore(BaseModel):
    score: float = Field(ge=0, le=10)
    max_score: float = Field(default=10, gt=0)
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    feedback: str = Field(default="", max_length=1000)


def validate_generated_question(question: GeneratedQuestion) -> None:
    allowed_types = {"SINGLE", "MULTIPLE", "TRUE_FALSE", "SHORT"}
    if question.question_type not in allowed_types:
        raise ValueError("QUIZ_QUESTION_TYPE_INVALID")
    if len(set(question.options)) != len(question.options):
        raise ValueError("QUIZ_OPTIONS_DUPLICATE")
    labels = {chr(65 + index) for index in range(len(question.options))}
    if any(answer not in question.options and answer not in labels and question.question_type != "SHORT" for answer in question.correct_answer):
        raise ValueError("QUIZ_CORRECT_ANSWER_INVALID")
    if question.question_type == "SINGLE" and (len(question.options) < 2 or len(question.correct_answer) != 1):
        raise ValueError("QUIZ_SINGLE_SCHEMA_INVALID")
    if question.question_type == "MULTIPLE" and (len(question.options) < 2 or len(question.correct_answer) < 2):
        raise ValueError("QUIZ_MULTIPLE_SCHEMA_INVALID")
    if question.question_type == "TRUE_FALSE" and sorted(question.options) != ["false", "true"]:
        raise ValueError("QUIZ_TRUE_FALSE_SCHEMA_INVALID")
    if question.question_type == "SHORT" and (not question.reference_answer or not question.scoring_points):
        raise ValueError("QUIZ_SHORT_SCHEMA_INVALID")


def normalize_choice_answers(options: list[str], answers: list[str]) -> list[str]:
    by_text = {str(option): chr(65 + index) for index, option in enumerate(options)}
    return [by_text.get(str(answer), str(answer)) for answer in answers]


def score_short_answer(question: QuizQuestion, answer: list[str]) -> tuple[int, bool, str]:
    provider = get_llm_provider()
    scorer = getattr(provider, "score_short_answer", None)
    if scorer is None:
        raise RuntimeError("LLM_SHORT_SCORING_UNSUPPORTED")
    try:
        result = asyncio.run(scorer(question.question, " ".join(answer), question.reference_answer, question.scoring_points, question.evidence))
        grading = ShortAnswerScore.model_validate(result)
    except Exception as error:
        raise HTTPException(503, "AI_PROVIDER_ERROR") from error
    ratio = min(1.0, max(0.0, grading.score / max(1.0, grading.max_score)))
    points = round(question.score_value * ratio)
    return points, points >= max(1, round(question.score_value * 0.6)), grading.feedback or f"覆盖 {len(grading.covered_points)}/{len(question.scoring_points)} 个评分点。"


class AnswersIn(BaseModel):
    answers: list[dict[str, Any]] = Field(default_factory=list)


def kb_json(db: Session, kb: KnowledgeBase) -> dict[str, Any]:
    documents = db.scalars(select(Document).where(Document.knowledge_base_id == kb.id, Document.user_id == kb.user_id, Document.deleted_at.is_(None))).all()
    chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb.id, DocumentChunk.user_id == kb.user_id)).all()
    return {"id": kb.id, "name": kb.name, "description": kb.description, "category": kb.category, "icon": kb.icon, "status": kb.status, "document_count": len(documents), "chunk_count": len(chunks), "updated_at": kb.updated_at.isoformat()}


app = FastAPI(title="StudyAgent API", version="1.0.0")
allowed_origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

_rate_limits: dict[str, list[float]] = {}


def check_rate_limit(key: str, limit: int) -> None:
    # ponytail: process-local window; use Redis atomic counters when horizontal scale matters.
    now = time.monotonic()
    recent = [stamp for stamp in _rate_limits.get(key, []) if stamp > now - 60]
    if len(recent) >= limit:
        raise HTTPException(429, "RATE_LIMITED")
    recent.append(now)
    _rate_limits[key] = recent


def dependency_error(error: Exception) -> str:
    code = str(error).split(":", 1)[0].strip()
    return code[:80] if re.fullmatch(r"[A-Z0-9_\-]+", code) else type(error).__name__


@app.on_event("startup")
def validate_production_startup() -> None:
    if not is_dev():
        validate_security_config()
        cors_origins = os.getenv("CORS_ORIGINS", "").strip()
        if not cors_origins:
            raise RuntimeError("CORS_ORIGINS_REQUIRED")
        if "*" in {origin.strip() for origin in cors_origins.split(",")}:
            raise RuntimeError("CORS_ORIGINS_WILDCARD")
        database_url = os.getenv("DATABASE_URL", DATABASE_URL).lower()
        if not database_url.startswith(("mysql://", "mysql+pymysql://")):
            raise RuntimeError("MYSQL_DATABASE_REQUIRED")
        if not os.getenv("REDIS_URL", "").strip():
            raise RuntimeError("REDIS_URL_REQUIRED")
        if not os.getenv("QDRANT_URL", "").strip():
            raise RuntimeError("QDRANT_URL_REQUIRED")
        get_storage()
        get_vector_store()
        get_llm_provider()
        get_embedding_provider()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(db_session)):
    dependencies: dict[str, str] = {}
    try:
        db.execute(select(User).limit(1))
        dependencies["database"] = "ok"
    except Exception as error:
        dependencies["database"] = dependency_error(error)
    if is_dev():
        dependencies.update({"redis": "dev-not-required", "storage": "ok", "qdrant": "dev-not-required", **validate_provider_config()})
    else:
        try:
            import socket
            from urllib.parse import urlparse
            redis_url = os.getenv("REDIS_URL", "").strip()
            if not redis_url:
                raise RuntimeError("REDIS_URL_REQUIRED")
            parsed = urlparse(redis_url)
            if parsed.scheme not in {"redis", "rediss"}:
                raise RuntimeError("REDIS_URL_INVALID")
            host, port = parsed.hostname or "localhost", parsed.port or 6379
            with socket.create_connection((host, port), timeout=2):
                dependencies["redis"] = "ok"
        except Exception as error:
            dependencies["redis"] = dependency_error(error)
        for name, getter in (("storage", get_storage), ("qdrant", get_vector_store)):
            try:
                service = getter()
                dependencies[name] = service.health()
            except Exception as error:
                dependencies[name] = dependency_error(error)
        dependencies.update(probe_provider_config())
    status = "ready" if all(value in {"ok", "dev-not-required"} for value in dependencies.values()) else "unhealthy"
    if status != "ready":
        raise HTTPException(503, {"code": "DEPENDENCY_UNAVAILABLE", "dependencies": dependencies})
    return {"status": status, "dependencies": dependencies}


@app.post("/api/v1/auth/dev-login")
def dev_login(payload: LoginIn, db: Session = Depends(db_session)):
    if not is_dev():
        raise HTTPException(404, "NOT_FOUND")
    nickname = payload.nickname.strip() or "学习者"
    check_rate_limit(f"login:{nickname}", 10)
    openid = f"dev-{hashlib.sha256(nickname.encode("utf-8")).hexdigest()[:32]}"
    user = db.scalar(select(User).where(User.openid == openid))
    if not user:
        user = User(nickname=nickname, openid=openid)
        db.add(user); db.commit(); db.refresh(user)
    return {"code": 0, "message": "ok", "data": {"access_token": token_for(user.id), "expires_in": token_expire_seconds(), "user": {"id": user.id, "nickname": user.nickname}}}


@app.post("/api/v1/auth/wechat/login")
def wechat_login(payload: dict[str, str], db: Session = Depends(db_session)):
    if is_dev():
        return dev_login(LoginIn(nickname="微信学习者"), db)
    if not os.getenv("WECHAT_APP_ID") or not os.getenv("WECHAT_APP_SECRET"):
        raise HTTPException(503, "WECHAT_PROVIDER_NOT_CONFIGURED")
    code = (payload.get("code") or "").strip()
    if not code: raise HTTPException(400, "WECHAT_CODE_REQUIRED")
    check_rate_limit(f"wechat-login:{hashlib.sha256(code.encode()).hexdigest()[:16]}", 5)
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
    return {"code": 0, "message": "ok", "data": {"access_token": token_for(user.id), "expires_in": token_expire_seconds(), "user": {"id": user.id, "nickname": user.nickname}}}


@app.get("/api/v1/auth/profile")
def profile(user: User = Depends(current_user)):
    return {"code": 0, "message": "ok", "data": {"id": user.id, "nickname": user.nickname, "avatar_url": user.avatar_url}}


@app.delete("/api/v1/auth/account")
def delete_account(user: User = Depends(current_user), db: Session = Depends(db_session)):
    knowledge_bases = db.scalars(select(KnowledgeBase).where(KnowledgeBase.user_id == user.id)).all()
    documents = db.scalars(select(Document).where(Document.user_id == user.id)).all()
    try:
        vector_store = get_vector_store()
        for knowledge_base in knowledge_bases:
            vector_store.delete_by_kb(user.id, knowledge_base.id)
        storage = get_storage()
        for document in documents:
            storage.delete(document.storage_key)
    except Exception as error:
        db.rollback()
        raise HTTPException(503, "ACCOUNT_CLEANUP_FAILED") from error

    quiz_ids = [quiz.id for quiz in db.scalars(select(Quiz).where(Quiz.user_id == user.id)).all()]
    db.execute(delete(Message).where(Message.user_id == user.id))
    db.execute(delete(Conversation).where(Conversation.user_id == user.id))
    if quiz_ids:
        db.execute(delete(QuizAnswer).where(QuizAnswer.user_id == user.id, QuizAnswer.quiz_id.in_(quiz_ids)))
        db.execute(delete(QuizQuestion).where(QuizQuestion.user_id == user.id, QuizQuestion.quiz_id.in_(quiz_ids)))
    db.execute(delete(Quiz).where(Quiz.user_id == user.id))
    db.execute(delete(WrongQuestion).where(WrongQuestion.user_id == user.id))
    db.execute(delete(Mastery).where(Mastery.user_id == user.id))
    db.execute(delete(StudyTask).where(StudyTask.user_id == user.id))
    db.execute(delete(StudyPlan).where(StudyPlan.user_id == user.id))
    db.execute(delete(AgentToolCall).where(AgentToolCall.user_id == user.id))
    db.execute(delete(AgentRun).where(AgentRun.user_id == user.id))
    db.execute(delete(UserMemory).where(UserMemory.user_id == user.id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.user_id == user.id))
    db.execute(delete(Document).where(Document.user_id == user.id))
    db.execute(delete(KnowledgeBase).where(KnowledgeBase.user_id == user.id))
    user.status = "DISABLED"
    user.nickname, user.avatar_url, user.openid = "已注销用户", None, None
    db.commit()
    return {"code": 0, "message": "ok", "data": {"deleted": True}}


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
    kb = owned(db, KnowledgeBase, kb_id, user.id)
    documents = db.scalars(select(Document).where(Document.knowledge_base_id == kb.id, Document.user_id == user.id, Document.deleted_at.is_(None))).all()
    try:
        get_vector_store().delete_by_kb(user.id, kb.id)
    except Exception as error:
        db.rollback()
        raise HTTPException(503, "DOCUMENT_CLEANUP_FAILED") from error
    for document in documents:
        try:
            get_storage().delete(document.storage_key)
        except Exception as error:
            db.rollback()
            raise HTTPException(503, "DOCUMENT_CLEANUP_FAILED") from error
        document.deleted_at = datetime.utcnow(); document.status = "DELETED"
    db.execute(delete(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb.id, DocumentChunk.user_id == user.id))
    kb.status = "DELETED"; db.commit()
    return {"code": 0, "message": "ok", "data": {"deleted": True}}


ALLOWED_EXT = {"pdf", "docx", "pptx", "txt", "md"}
MIME_BY_EXT = {"pdf": {"application/pdf", "application/octet-stream"}, "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", "application/octet-stream"}, "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip", "application/octet-stream"}, "txt": {"text/plain", "text/markdown", "application/octet-stream", ""}, "md": {"text/markdown", "text/plain", "application/octet-stream", ""}}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


async def read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "DOCUMENT_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


def validate_file(data: bytes, extension: str, content_type: str | None) -> None:
    if not data:
        return
    if content_type and content_type not in MIME_BY_EXT[extension]:
        raise HTTPException(415, "DOCUMENT_MIME_MISMATCH")
    if extension == "pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(415, "DOCUMENT_SIGNATURE_MISMATCH")
    if extension in {"txt", "md"} and b"\x00" in data[:4096]:
        raise HTTPException(415, "DOCUMENT_SIGNATURE_MISMATCH")
    if extension in {"docx", "pptx"} and not data.startswith(b"PK"):
        raise HTTPException(415, "DOCUMENT_SIGNATURE_MISMATCH")
    if extension in {"docx", "pptx"}:
        import zipfile
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
                if len(archive.infolist()) > 5000 or sum(item.file_size for item in archive.infolist()) > 200 * 1024 * 1024:
                    raise HTTPException(413, "DOCUMENT_ARCHIVE_TOO_LARGE")
                compressed = max(1, sum(item.compress_size for item in archive.infolist()))
                if sum(item.file_size for item in archive.infolist()) / compressed > 1000:
                    raise HTTPException(413, "DOCUMENT_ARCHIVE_COMPRESSION_RATIO")
                if extension == "docx" and "word/document.xml" not in archive.namelist():
                    raise HTTPException(415, "DOCUMENT_SIGNATURE_MISMATCH")
                if extension == "pptx" and "ppt/presentation.xml" not in archive.namelist():
                    raise HTTPException(415, "DOCUMENT_SIGNATURE_MISMATCH")
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(415, "DOCUMENT_INVALID_ARCHIVE") from error


@app.post("/api/v1/knowledge-bases/{kb_id}/documents")
async def upload_document(kb_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(db_session)):
    check_rate_limit(f"upload:{user.id}", 20)
    owned(db, KnowledgeBase, kb_id, user.id)
    extension = Path(file.filename or "").suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXT:
        raise HTTPException(415, "DOCUMENT_UNSUPPORTED")
    data = await read_upload(file)
    validate_file(data, extension, file.content_type)
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.knowledge_base_id == kb_id, Document.sha256 == digest, Document.deleted_at.is_(None)))
    if existing:
        return {"code": 0, "message": "ok", "data": document_json(existing)}
    document = Document(user_id=user.id, knowledge_base_id=kb_id, filename=Path(file.filename or "document").name, original_filename=file.filename or "document", mime_type=file.content_type or "application/octet-stream", extension=extension, sha256=digest, size_bytes=len(data), status="PARSING")
    db.add(document); db.flush()
    document.storage_key = get_storage().put(user.id, kb_id, document.filename, data)
    if not data:
        document.status = "FAILED"; document.failure_message = "DOCUMENT_EMPTY"; db.commit()
        return {"code": 0, "message": "ok", "data": document_json(document)}
    if not is_dev():
        document.status = "UPLOADED"; db.commit()
        from .worker import process_document
        try:
            process_document.delay(document.id)
        except Exception as error:
            document.status = "FAILED"
            document.failure_message = "DOCUMENT_QUEUE_UNAVAILABLE"
            db.commit()
            raise HTTPException(503, "DOCUMENT_QUEUE_UNAVAILABLE") from error
        return {"code": 0, "message": "ok", "data": document_json(document)}
    db.commit()
    from .worker import process_document
    try:
        await asyncio.to_thread(process_document, document.id)
    except Exception:
        db.rollback()
    document = db.get(Document, document.id)
    db.refresh(document)
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


async def retrieve_chunks(db: Session, user_id: int, knowledge_base_id: int, query: str, score_threshold: float | None = None) -> list[dict[str, Any]]:
    embedding = get_embedding_provider()
    vector = await embedding.embed_query(query)
    store = get_vector_store()
    store.ensure_collection(len(vector))
    threshold = float(os.getenv("RAG_SCORE_THRESHOLD", "0.35")) if score_threshold is None else score_threshold
    hits = store.search(vector, user_id, knowledge_base_id, limit=int(os.getenv("RAG_TOP_K", "6")), score_threshold=threshold)
    if not hits:
        return []
    valid_hits = []
    for item in hits:
        try:
            int(item["payload"].get("document_id", -1))
            int(item["payload"].get("chunk_id", -1))
        except (TypeError, ValueError):
            continue
        valid_hits.append(item)
    hits = valid_hits
    if not hits:
        return []
    chunk_ids = [int(item["payload"].get("chunk_id", -1)) for item in hits]
    document_ids = [int(item["payload"].get("document_id", -1)) for item in hits]
    chunks = db.scalars(select(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id).where(DocumentChunk.user_id == user_id, DocumentChunk.knowledge_base_id == knowledge_base_id, DocumentChunk.document_id.in_(document_ids), Document.deleted_at.is_(None), Document.status == "READY")).all()
    by_key = {(chunk.document_id, chunk.chunk_index): chunk for chunk in chunks}
    results = []
    for hit, chunk_index in zip(hits, chunk_ids):
        chunk = by_key.get((int(hit["payload"].get("document_id", -1)), chunk_index))
        if chunk:
            results.append({"chunk": chunk, "score": hit["score"]})
    return results


def document_json(document: Document) -> dict[str, Any]:
    return {"id": document.id, "filename": document.filename, "original_filename": document.original_filename, "mime_type": document.mime_type, "extension": document.extension, "status": document.status, "size_bytes": document.size_bytes, "failure_message": document.failure_message}


@app.get("/api/v1/knowledge-bases/{kb_id}/documents")
def list_documents(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, kb_id, user.id)
    items = [document_json(d) for d in db.scalars(select(Document).where(Document.knowledge_base_id == kb_id, Document.user_id == user.id, Document.deleted_at.is_(None))).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


@app.get("/api/v1/documents/{document_id}/status")
def document_status(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {"code": 0, "message": "ok", "data": document_json(owned(db, Document, document_id, user.id))}


@app.get("/api/v1/documents/{document_id}")
def get_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return {"code": 0, "message": "ok", "data": document_json(owned(db, Document, document_id, user.id))}


@app.delete("/api/v1/documents/{document_id}")
def delete_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    document = owned(db, Document, document_id, user.id)
    try:
        get_vector_store().delete_by_document(user.id, document.id)
        get_storage().delete(document.storage_key)
    except Exception as error:
        db.rollback()
        raise HTTPException(503, "DOCUMENT_CLEANUP_FAILED") from error
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id, DocumentChunk.user_id == user.id))
    document.deleted_at = datetime.utcnow()
    document.status = "DELETED"
    db.commit()
    return {"code": 0, "message": "ok", "data": {"deleted": True}}


@app.post("/api/v1/documents/{document_id}/retry")
def retry_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    document = owned(db, Document, document_id, user.id)
    document.status = "PARSING"
    document.failure_message = None
    db.commit()
    from .worker import process_document
    if is_dev():
        try:
            process_document(document.id)
        except Exception:
            pass
    else:
        document.status = "UPLOADED"; db.commit()
        try:
            process_document.delay(document.id)
        except Exception as error:
            document.status = "FAILED"
            document.failure_message = "DOCUMENT_QUEUE_UNAVAILABLE"
            db.commit()
            raise HTTPException(503, "DOCUMENT_QUEUE_UNAVAILABLE") from error
    db.refresh(document)
    return {"code": 0, "message": "ok", "data": document_json(document)}


@app.post("/api/v1/documents/{document_id}/rebuild")
def rebuild_document(document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    return retry_document(document_id, user, db)


class ConversationIn(BaseModel):
    knowledge_base_id: int


@app.post("/api/v1/conversations")
def create_conversation(payload: ConversationIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    conversation = Conversation(user_id=user.id, knowledge_base_id=payload.knowledge_base_id); db.add(conversation); db.commit(); db.refresh(conversation)
    return {"code": 0, "message": "ok", "data": {"id": conversation.id, "title": conversation.title, "knowledge_base_id": conversation.knowledge_base_id}}


@app.get("/api/v1/conversations")
def list_conversations(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [{"id": c.id, "title": c.title, "knowledge_base_id": c.knowledge_base_id} for c in db.scalars(select(Conversation).where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None)).order_by(Conversation.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.delete("/api/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    conversation = owned(db, Conversation, conversation_id, user.id); conversation.deleted_at = datetime.utcnow(); db.commit(); return {"code": 0, "message": "ok", "data": {"deleted": True}}


@app.get("/api/v1/conversations/{conversation_id}/messages")
def messages(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, Conversation, conversation_id, user.id)
    items = [{"id": m.id, "role": m.role, "content": m.content, "citations": m.citations or []} for m in db.scalars(select(Message).where(Message.conversation_id == conversation_id, Message.user_id == user.id).order_by(Message.created_at)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.post("/api/v1/conversations/{conversation_id}/messages")
async def chat(conversation_id: int, payload: ChatIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    check_rate_limit(f"chat:{user.id}", 30)
    conversation = owned(db, Conversation, conversation_id, user.id)
    db.add(Message(user_id=user.id, conversation_id=conversation_id, role="USER", content=payload.content)); db.flush()
    try:
        hits = await retrieve_chunks(db, user.id, conversation.knowledge_base_id, payload.content)
        result = await get_llm_provider().chat(payload.content, [item["chunk"].content for item in hits])
    except Exception as error:
        db.rollback()
        raise HTTPException(503, "AI_PROVIDER_ERROR") from error
    answer = result["content"]
    citations = []
    for index in result.get("citations", []):
        if index >= len(hits):
            continue
        chunk = hits[index]["chunk"]
        document = db.get(Document, chunk.document_id)
        citations.append({"document_id": chunk.document_id, "document_name": document.filename if document else "", "chunk_id": chunk.id, "page_start": chunk.page_start, "quote_text": chunk.content[:240], "score": round(hits[index]["score"], 4)})
    assistant = Message(user_id=user.id, conversation_id=conversation_id, role="ASSISTANT", content=answer, citations=citations); db.add(assistant); db.commit(); db.refresh(assistant)
    return {"code": 0, "message": "ok", "data": {"id": assistant.id, "content": answer, "citations": citations, "status": "COMPLETED"}}


@app.websocket("/ws/v1/chat/{conversation_id}")
async def chat_stream(websocket: WebSocket, conversation_id: int):
    token = websocket.query_params.get("token", "")
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", SECRET), algorithms=["HS256"])
        user_id = int(payload["user_id"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        await websocket.close(code=4401); return
    with SessionLocal() as db:
        user = db.get(User, user_id)
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id, Conversation.deleted_at.is_(None)))
        if not conversation or not user or user.status != "ACTIVE":
            await websocket.close(code=4404); return
    await websocket.accept()
    try:
        request = await websocket.receive_json()
        question = str(request.get("content", "")).strip()
        if not question:
            await websocket.close(code=4400)
            return
        await websocket.send_json({"type": "retrieval_started"})
        with SessionLocal() as db:
            db.add(Message(user_id=user_id, conversation_id=conversation_id, role="USER", content=question))
            db.commit()
            hits = await retrieve_chunks(db, user_id, conversation.knowledge_base_id, question)
            document_names = {
                chunk.document_id: document.filename
                for chunk in (item["chunk"] for item in hits)
                if (document := db.get(Document, chunk.document_id))
            }
        await websocket.send_json({"type": "retrieval_finished", "count": len(hits)})
        parts: list[str] = []
        async for part in get_llm_provider().stream_chat(question, [item["chunk"].content for item in hits]):
            parts.append(part)
            await websocket.send_json({"type": "token", "content": part})
        citation_items = [{"document_id": item["chunk"].document_id, "document_name": document_names.get(item["chunk"].document_id, ""), "chunk_id": item["chunk"].id, "page_start": item["chunk"].page_start, "quote_text": item["chunk"].content[:240], "score": item["score"]} for item in hits]
        with SessionLocal() as db:
            assistant = Message(user_id=user_id, conversation_id=conversation_id, role="ASSISTANT", content="".join(parts), citations=citation_items)
            db.add(assistant); db.commit(); db.refresh(assistant)
            message_id = assistant.id
        for item in hits:
            chunk = item["chunk"]
            await websocket.send_json({"type": "citation", "data": {"document_id": chunk.document_id, "document_name": document_names.get(chunk.document_id, ""), "chunk_id": chunk.id, "page_start": chunk.page_start, "quote_text": chunk.content[:240], "score": item["score"]}})
        await websocket.send_json({"type": "done", "message_id": message_id})
    except WebSocketDisconnect:
        return


@app.post("/api/v1/study-plans")
async def create_plan(payload: PlanIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    check_rate_limit(f"plan:{user.id}", 10)
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    try:
        plan_today = datetime.now(ZoneInfo(payload.timezone)).date()
    except Exception as error:
        raise HTTPException(422, "TIMEZONE_INVALID") from error
    if payload.target_date < plan_today:
        raise HTTPException(422, "PLAN_INVALID_DATE")
    hits = await retrieve_chunks(db, user.id, payload.knowledge_base_id, payload.goal or "生成学习计划", score_threshold=-1.0)
    if not hits:
        raise HTTPException(422, "KNOWLEDGE_BASE_NO_RELIABLE_MATERIAL")
    try:
        generated = await get_llm_provider().structured_output(f"请根据资料生成学习计划草案，目标是：{payload.goal}", GeneratedPlan.model_json_schema(), [item["chunk"].content for item in hits])
        generated_plan = GeneratedPlan.model_validate(generated)
    except Exception as error:
        raise HTTPException(503, "AI_PROVIDER_ERROR") from error
    values = payload.model_dump(exclude={"timezone"})
    if generated_plan.plan_name:
        values["name"] = generated_plan.plan_name
    values["generated_schedule"] = [day.model_dump() for day in generated_plan.days]
    plan = StudyPlan(user_id=user.id, timezone=payload.timezone, **values); db.add(plan); db.commit(); db.refresh(plan)
    return {"code": 0, "message": "ok", "data": plan_json(plan)}


@app.get("/api/v1/study-plans")
def list_plans(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [plan_json(plan) for plan in db.scalars(select(StudyPlan).where(StudyPlan.user_id == user.id).order_by(StudyPlan.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


def plan_json(plan: StudyPlan) -> dict[str, Any]:
    return {"id": plan.id, "name": plan.name, "goal": plan.goal, "knowledge_base_id": plan.knowledge_base_id, "target_date": plan.target_date.isoformat(), "daily_minutes": plan.daily_minutes, "weekly_days": plan.weekly_days, "foundation_level": plan.foundation_level, "intensity": plan.intensity, "timezone": plan.timezone, "status": plan.status, "progress_percent": plan.progress_percent, "generated_by_ai": plan.generated_by_ai, "schedule": plan.generated_schedule or [], "ai_notice": "AI 生成 · 请核验重要信息"}


@app.post("/api/v1/study-plans/{plan_id}/activate")
def activate_plan(plan_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    plan = owned(db, StudyPlan, plan_id, user.id)
    if plan.status == "ACTIVE":
        return {"code": 0, "message": "ok", "data": plan_json(plan)}
    plan.status = "ACTIVE"
    existing_dates = {task.scheduled_date for task in db.scalars(select(StudyTask).where(StudyTask.study_plan_id == plan.id, StudyTask.user_id == user.id)).all()}
    try:
        cursor = datetime.now(ZoneInfo(plan.timezone)).date()
    except Exception as error:
        raise HTTPException(422, "TIMEZONE_INVALID") from error
    end = min(plan.target_date, cursor + timedelta(days=365))
    schedule = plan.generated_schedule or []
    created = 0
    for day in schedule:
        try:
            scheduled = date.fromisoformat(str(day.get("date", "")))
        except (TypeError, ValueError):
            scheduled = cursor
        if scheduled < cursor or scheduled > end or scheduled in existing_dates:
            continue
        task = (day.get("tasks") or [{}])[0]
        title = str(task.get("title") or day.get("goal") or plan.goal or plan.name).strip()[:200]
        if not title:
            continue
        task_type = str(task.get("type") or "LEARN_POINT")[:30]
        estimated = task.get("estimated_minutes") or day.get("estimated_minutes") or plan.daily_minutes
        db.add(StudyTask(user_id=user.id, study_plan_id=plan.id, knowledge_base_id=plan.knowledge_base_id, task_type=task_type, title=title, description=str(day.get("goal") or plan.goal)[:500], estimated_minutes=max(5, min(480, int(estimated))), scheduled_date=scheduled))
        existing_dates.add(scheduled)
        created += 1
        cursor = max(cursor, scheduled + timedelta(days=1))
    while cursor <= end and created == 0:
        if cursor.weekday() < plan.weekly_days and cursor not in existing_dates:
            db.add(StudyTask(user_id=user.id, study_plan_id=plan.id, knowledge_base_id=plan.knowledge_base_id, task_type="LEARN_POINT", title=(plan.goal or plan.name)[:200], description=plan.goal[:500], estimated_minutes=plan.daily_minutes, scheduled_date=cursor))
            created += 1
        cursor += timedelta(days=1)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        plan = owned(db, StudyPlan, plan_id, user.id)
        if plan.status != "ACTIVE":
            raise HTTPException(409, "PLAN_ACTIVATION_CONFLICT")
    return {"code": 0, "message": "ok", "data": plan_json(plan)}


@app.get("/api/v1/tasks/today")
def today_tasks(timezone_name: str = Query("Asia/Shanghai", alias="timezone"), user: User = Depends(current_user), db: Session = Depends(db_session)):
    try:
        local_today = datetime.now(ZoneInfo(timezone_name)).date()
    except Exception as error:
        raise HTTPException(422, "TIMEZONE_INVALID") from error
    items = [task_json(t) for t in db.scalars(select(StudyTask).where(StudyTask.user_id == user.id, StudyTask.scheduled_date == local_today).order_by(StudyTask.id)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items, "total": len(items)}}


def task_json(task: StudyTask) -> dict[str, Any]:
    return {"id": task.id, "title": task.title, "description": task.description, "task_type": task.task_type, "estimated_minutes": task.estimated_minutes, "actual_minutes": task.actual_minutes, "scheduled_date": task.scheduled_date.isoformat(), "status": task.status}


def refresh_plan_progress(db: Session, user_id: int, knowledge_base_id: int) -> None:
    plans = db.scalars(select(StudyPlan).where(StudyPlan.user_id == user_id, StudyPlan.knowledge_base_id == knowledge_base_id, StudyPlan.status == "ACTIVE")).all()
    for plan in plans:
        tasks = db.scalars(select(StudyTask).where(StudyTask.study_plan_id == plan.id, StudyTask.user_id == user_id)).all()
        plan.progress_percent = round(sum(task.status == "DONE" for task in tasks) / max(1, len(tasks)) * 100)


def adjust_plan_after_quiz(db: Session, user_id: int, knowledge_base_id: int, wrong_topics: list[str]) -> None:
    if not wrong_topics:
        return
    topic_text = "、".join(dict.fromkeys(topic[:80] for topic in wrong_topics))[:300]
    for plan in db.scalars(select(StudyPlan).where(StudyPlan.user_id == user_id, StudyPlan.knowledge_base_id == knowledge_base_id, StudyPlan.status == "ACTIVE")).all():
        try:
            today = datetime.now(ZoneInfo(plan.timezone)).date()
        except Exception:
            continue
        tasks = db.scalars(select(StudyTask).where(StudyTask.study_plan_id == plan.id, StudyTask.user_id == user_id).order_by(StudyTask.scheduled_date, StudyTask.id)).all()
        future = next((task for task in tasks if task.status != "DONE" and task.scheduled_date > today), None)
        if future:
            future.description = f"{future.description} 重点复习：{topic_text}"[:500]
            continue
        next_date = today + timedelta(days=1)
        occupied = {task.scheduled_date for task in tasks}
        while next_date in occupied and next_date <= plan.target_date:
            next_date += timedelta(days=1)
        if next_date <= plan.target_date:
            db.add(StudyTask(user_id=user_id, study_plan_id=plan.id, knowledge_base_id=knowledge_base_id, task_type="REVIEW", title="复习薄弱知识点", description=f"重点复习：{topic_text}", estimated_minutes=plan.daily_minutes, scheduled_date=next_date))


@app.post("/api/v1/tasks/{task_id}/complete")
def complete_task(task_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    task = owned(db, StudyTask, task_id, user.id)
    if task.status != "DONE":
        task.status = "DONE"; task.completed_at = datetime.utcnow(); task.actual_minutes = task.actual_minutes or task.estimated_minutes
        refresh_plan_progress(db, user.id, task.knowledge_base_id)
        db.commit()
    return {"code": 0, "message": "ok", "data": task_json(task)}


@app.post("/api/v1/quizzes")
async def create_quiz(payload: QuizIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    check_rate_limit(f"quiz:{user.id}", 10)
    owned(db, KnowledgeBase, payload.knowledge_base_id, user.id)
    supported = {"SINGLE", "MULTIPLE", "TRUE_FALSE", "SHORT"}
    if not payload.question_types or any(item not in supported for item in payload.question_types):
        raise HTTPException(422, "QUIZ_QUESTION_TYPE_INVALID")
    if payload.study_task_id is not None:
        owned(db, StudyTask, payload.study_task_id, user.id)
    hits = await retrieve_chunks(db, user.id, payload.knowledge_base_id, "生成测验", score_threshold=-1.0)
    contexts = [item["chunk"].content for item in hits]
    if not contexts:
        raise HTTPException(422, "KNOWLEDGE_BASE_NO_RELIABLE_MATERIAL")
    try:
        generated = await get_llm_provider().structured_output("请根据资料生成一组学习测验，题目必须可由资料证据回答。", GeneratedQuestion.model_json_schema(), contexts)
        generated_questions = [GeneratedQuestion.model_validate(item) for item in generated.get("questions", [])]
        for generated_question in generated_questions:
            validate_generated_question(generated_question)
    except Exception as error:
        raise HTTPException(503, "AI_PROVIDER_ERROR") from error
    if not generated_questions:
        raise HTTPException(503, "AI_PROVIDER_INVALID_RESPONSE")
    quiz = Quiz(user_id=user.id, knowledge_base_id=payload.knowledge_base_id, question_count=payload.question_count, max_score=payload.question_count * 20); db.add(quiz); db.flush()
    kinds = payload.question_types
    hit_by_id = {item["chunk"].id: item for item in hits}
    for i in range(payload.question_count):
        kind = kinds[i % len(kinds)]
        generated_question = generated_questions[i % len(generated_questions)]
        source = generated_question.model_dump()
        question_type_matches = generated_question.question_type == kind
        evidence_hit = next((hit_by_id[chunk_id] for chunk_id in generated_question.source_chunk_ids if chunk_id in hit_by_id), None)
        evidence = evidence_hit["chunk"].content if evidence_hit else contexts[i % len(contexts)]
        if question_type_matches:
            options, correct = generated_question.options, normalize_choice_answers(generated_question.options, generated_question.correct_answer)
        elif kind == "MULTIPLE":
            options, correct = [evidence[:120], "资料未提及的内容", "与资料相反的说法", "无法判断的内容"], ["A"]
        elif kind == "TRUE_FALSE":
            options, correct = ["true", "false"], ["true"]
        elif kind == "SHORT":
            options, correct = [], []
        else:
            options, correct = [evidence[:120], "资料未提及的内容", "与资料相反的说法", "无法从资料判断"], ["A"]
        question_text = generated_question.question
        if i:
            question_text = f"{question_text}（第 {i + 1} 题）"
        db.add(QuizQuestion(quiz_id=quiz.id, user_id=user.id, question_type=kind, question=question_text, options=options, correct_answer=correct, explanation=source.get("explanation") or "请结合资料证据核验。", reference_answer=source.get("reference_answer") or evidence, scoring_points=source.get("scoring_points") or [evidence[:80]], evidence=evidence, source_chunk_ids=[evidence_hit["chunk"].id] if evidence_hit else [hits[i % len(hits)]["chunk"].id], difficulty=payload.difficulty, score_value=20))
    db.commit(); return {"code": 0, "message": "ok", "data": quiz_json(db, quiz, reveal=False)}


def quiz_json(db: Session, quiz: Quiz, reveal: bool) -> dict[str, Any]:
    questions = []
    answers = {answer.question_id: answer for answer in db.scalars(select(QuizAnswer).where(QuizAnswer.quiz_id == quiz.id, QuizAnswer.user_id == quiz.user_id)).all()} if reveal else {}
    for q in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id).order_by(QuizQuestion.id)).all():
        item = {"id": q.id, "question_type": q.question_type, "question": q.question, "options": q.options, "score_value": q.score_value}
        if reveal:
            answer = answers.get(q.id)
            item.update({"correct_answer": q.correct_answer, "explanation": q.explanation, "reference_answer": q.reference_answer, "evidence": q.evidence, "user_answer": answer.answer if answer else [], "is_correct": bool(answer and answer.is_correct), "score": answer.score if answer else 0, "ai_feedback": answer.ai_feedback if answer else ""})
        questions.append(item)
    return {"id": quiz.id, "title": quiz.title, "status": quiz.status, "question_count": quiz.question_count, "max_score": quiz.max_score, "questions": questions, "ai_notice": "AI 生成 · 请核验重要信息"}


@app.get("/api/v1/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    quiz = owned(db, Quiz, quiz_id, user.id); return {"code": 0, "message": "ok", "data": quiz_json(db, quiz, reveal=quiz.status == "SUBMITTED")}


@app.post("/api/v1/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: int, payload: AnswersIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    quiz = owned(db, Quiz, quiz_id, user.id)
    if quiz.status != "ACTIVE": raise HTTPException(409, "QUIZ_ALREADY_SUBMITTED")
    questions = {q.id: q for q in db.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id, QuizQuestion.user_id == user.id)).all()}
    submitted = {}
    for answer in payload.answers:
        try:
            question_id = int(answer.get("question_id", 0))
        except (TypeError, ValueError):
            raise HTTPException(422, "QUIZ_ANSWER_INVALID")
        if question_id in submitted:
            raise HTTPException(422, "QUIZ_DUPLICATE_ANSWER")
        if question_id not in questions:
            raise HTTPException(422, "QUIZ_QUESTION_NOT_FOUND")
        value = answer.get("answer", [])
        submitted[question_id] = [str(value)] if isinstance(value, str) else [str(item) for item in (value or [])]
    short_scores = {question_id: score_short_answer(question, submitted.get(question_id, [])) for question_id, question in questions.items() if question.question_type == "SHORT"}
    claimed = db.execute(update(Quiz).where(Quiz.id == quiz.id, Quiz.user_id == user.id, Quiz.status == "ACTIVE").values(status="SUBMITTING"))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "QUIZ_ALREADY_SUBMITTED")
    # Commit the claim before grading so a concurrent request observes SUBMITTING.
    db.commit()
    try:
        score = 0
        wrong_topics = []
        for question_id, q in questions.items():
            given = submitted.get(question_id, [])
            if q.question_type == "SHORT":
                points, is_correct, feedback = short_scores[question_id]
            else:
                correct = sorted(map(str, q.correct_answer)); normalized = sorted(given)
                is_correct = normalized == correct
                points = q.score_value if is_correct else 0
                feedback = "答案与参考答案一致。" if is_correct else "未覆盖全部正确选项。"
            score += points
            db.add(QuizAnswer(quiz_id=quiz.id, question_id=q.id, user_id=user.id, answer=given, is_correct=is_correct, score=points, ai_feedback=feedback))
            if not is_correct:
                wrong_topics.append(q.question)
                wrong = db.scalar(select(WrongQuestion).where(WrongQuestion.user_id == user.id, WrongQuestion.question_id == q.id))
                if wrong:
                    wrong.wrong_count += 1; wrong.last_wrong_at = datetime.utcnow(); wrong.mastered = False
                else:
                    db.add(WrongQuestion(user_id=user.id, question_id=q.id, knowledge_base_id=quiz.knowledge_base_id))
            topic = q.question[:120]
            mastery = db.scalar(select(Mastery).where(Mastery.user_id == user.id, Mastery.knowledge_base_id == quiz.knowledge_base_id, Mastery.topic == topic))
            if not mastery:
                mastery = Mastery(user_id=user.id, knowledge_base_id=quiz.knowledge_base_id, topic=topic, mastery_score=50); db.add(mastery); db.flush()
            mastery.quiz_count += 1; mastery.correct_count += int(is_correct); mastery.last_reviewed_at = datetime.utcnow(); mastery.mastery_score = max(0, min(100, mastery.mastery_score + (6 if is_correct else -8)))
        adjust_plan_after_quiz(db, user.id, quiz.knowledge_base_id, wrong_topics)
        refresh_plan_progress(db, user.id, quiz.knowledge_base_id)
        quiz.status = "SUBMITTED"; quiz.score = score; quiz.max_score = sum(q.score_value for q in questions.values()); quiz.submitted_at = datetime.utcnow(); db.commit()
    except Exception as error:
        db.rollback()
        db.execute(update(Quiz).where(Quiz.id == quiz.id, Quiz.user_id == user.id, Quiz.status == "SUBMITTING").values(status="ACTIVE"))
        db.commit()
        raise HTTPException(503, "QUIZ_SUBMISSION_FAILED") from error
    return {"code": 0, "message": "ok", "data": {"score": score, "max_score": quiz.max_score, "correct_rate": round(score / max(1, quiz.max_score) * 100), "quiz": quiz_json(db, quiz, reveal=True)}}


@app.get("/api/v1/knowledge-bases/{kb_id}/mastery")
def mastery_list(kb_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    owned(db, KnowledgeBase, kb_id, user.id)
    items = [{"topic": m.topic, "mastery_score": m.mastery_score, "level": "薄弱" if m.mastery_score < 40 else "待加强" if m.mastery_score < 60 else "基本掌握" if m.mastery_score < 80 else "熟练"} for m in db.scalars(select(Mastery).where(Mastery.user_id == user.id, Mastery.knowledge_base_id == kb_id)).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.get("/api/v1/dashboard")
def dashboard(timezone_name: str = Query("Asia/Shanghai", alias="timezone"), user: User = Depends(current_user), db: Session = Depends(db_session)):
    try:
        zone = ZoneInfo(timezone_name)
        today = datetime.now(zone).date()
    except Exception as error:
        raise HTTPException(422, "TIMEZONE_INVALID") from error
    week_start = today - timedelta(days=6)
    tasks_today = db.scalars(select(StudyTask).where(StudyTask.user_id == user.id, StudyTask.scheduled_date == today)).all()
    tasks_week = db.scalars(select(StudyTask).where(StudyTask.user_id == user.id, StudyTask.scheduled_date >= week_start, StudyTask.scheduled_date <= today)).all()
    answers = db.scalars(select(QuizAnswer).where(QuizAnswer.user_id == user.id)).all()
    recent_answers = [answer for answer in answers if answer.created_at and (answer.created_at.replace(tzinfo=timezone.utc) if answer.created_at.tzinfo is None else answer.created_at).astimezone(zone).date() >= week_start]
    mastery = db.scalars(select(Mastery).where(Mastery.user_id == user.id)).all()
    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        day_tasks = [task for task in tasks_week if task.scheduled_date == day]
        trend.append({"date": day.isoformat(), "minutes": sum(task.actual_minutes or (task.estimated_minutes if task.status == "DONE" else 0) for task in day_tasks), "tasks_done": sum(task.status == "DONE" for task in day_tasks)})
    total = len(recent_answers)
    return {"code": 0, "message": "ok", "data": {"today_minutes": sum(task.actual_minutes or (task.estimated_minutes if task.status == "DONE" else 0) for task in tasks_today), "week_minutes": sum(task.actual_minutes or (task.estimated_minutes if task.status == "DONE" else 0) for task in tasks_week), "task_total": len(tasks_today), "task_done": sum(task.status == "DONE" for task in tasks_today), "weekly_task_completion": round(sum(task.status == "DONE" for task in tasks_week) / max(1, len(tasks_week)) * 100), "weekly_accuracy": round(sum(answer.is_correct for answer in recent_answers) / max(1, total) * 100), "weak_points": [item.topic for item in mastery if item.mastery_score < 60], "mastery": [{"topic": item.topic, "score": item.mastery_score} for item in mastery], "trend": trend}}


class AgentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TodayTasksArgs(AgentArgs):
    timezone: str = "Asia/Shanghai"


class CompleteTaskArgs(AgentArgs):
    task_id: int = Field(ge=1)


class KnowledgeBaseSummaryArgs(AgentArgs):
    knowledge_base_id: int = Field(ge=1)


class NoAgentArgs(AgentArgs):
    pass


AGENT_ARGUMENT_MODELS = {
    "get_today_tasks": TodayTasksArgs,
    "complete_study_task": CompleteTaskArgs,
    "get_learning_progress": NoAgentArgs,
    "get_knowledge_base_summary": KnowledgeBaseSummaryArgs,
}


@app.get("/api/v1/agent/tools")
def agent_tools(user: User = Depends(current_user)):
    tools = [{"name": name, "arguments": model.model_json_schema()} for name, model in AGENT_ARGUMENT_MODELS.items()]
    return {"code": 0, "message": "ok", "data": {"tools": tools}}


class AgentExecuteIn(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/agent/execute")
def agent_execute(payload: AgentExecuteIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    run = AgentRun(user_id=user.id, input_text=payload.tool_name); db.add(run); db.flush()
    try:
        argument_model = AGENT_ARGUMENT_MODELS.get(payload.tool_name)
        if not argument_model:
            raise HTTPException(400, "AGENT_TOOL_NOT_ALLOWED")
        try:
            arguments = argument_model.model_validate(payload.arguments)
        except ValidationError as error:
            raise HTTPException(422, "AGENT_ARGUMENTS_INVALID") from error
        if payload.tool_name == "get_today_tasks":
            result = today_tasks(arguments.timezone, user, db)["data"]
        elif payload.tool_name == "get_learning_progress":
            result = dashboard("Asia/Shanghai", user, db)["data"]
        elif payload.tool_name == "get_knowledge_base_summary":
            result = kb_json(db, owned(db, KnowledgeBase, arguments.knowledge_base_id, user.id))
        elif payload.tool_name == "complete_study_task":
            result = complete_task(arguments.task_id, user, db)["data"]
        db.add(AgentToolCall(agent_run_id=run.id, user_id=user.id, tool_name=payload.tool_name, arguments_json=payload.arguments, result_summary=json.dumps(result, ensure_ascii=False)[:255], status="COMPLETED")); db.commit()
        response_data = {"tool_name": payload.tool_name, "result": result}
        if payload.tool_name == "complete_study_task":
            response_data["task"] = result
        return {"code": 0, "message": "ok", "data": response_data}
    except HTTPException:
        run.status = "FAILED"
        db.add(AgentToolCall(agent_run_id=run.id, user_id=user.id, tool_name=payload.tool_name, arguments_json=payload.arguments, result_summary="failed", status="FAILED")); db.commit()
        raise
    except Exception as error:
        run.status = "FAILED"; db.add(AgentToolCall(agent_run_id=run.id, user_id=user.id, tool_name=payload.tool_name, arguments_json=payload.arguments, result_summary=str(error)[:255], status="FAILED")); db.commit()
        raise HTTPException(400, "AGENT_TOOL_FAILED") from error


@app.get("/api/v1/agent/runs")
def agent_runs(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = [{"id": run.id, "agent_name": run.agent_name, "status": run.status, "created_at": run.created_at.isoformat()} for run in db.scalars(select(AgentRun).where(AgentRun.user_id == user.id).order_by(AgentRun.created_at.desc())).all()]
    return {"code": 0, "message": "ok", "data": {"items": items}}


class MemoryIn(BaseModel):
    memory_type: str = Field(min_length=1, max_length=40)
    memory_key: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)
    importance: int = Field(default=1, ge=1, le=5)


class MemoryExtractIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = Field(default=None, ge=1)


class MemoryExtractOutput(BaseModel):
    memories: list[MemoryIn] = Field(default_factory=list, max_length=20)


@app.get("/api/v1/memories")
def list_memories(user: User = Depends(current_user), db: Session = Depends(db_session)):
    items = db.scalars(select(UserMemory).where(UserMemory.user_id == user.id, (UserMemory.expires_at.is_(None) | (UserMemory.expires_at > datetime.utcnow()))).order_by(UserMemory.updated_at.desc())).all()
    return {"code": 0, "message": "ok", "data": {"items": [{"id": item.id, "memory_type": item.memory_type, "memory_key": item.memory_key, "content": item.content, "importance": item.importance} for item in items]}}


@app.post("/api/v1/memories")
def upsert_memory(payload: MemoryIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = db.scalar(select(UserMemory).where(UserMemory.user_id == user.id, UserMemory.memory_key == payload.memory_key))
    if memory:
        memory.memory_type, memory.content, memory.importance = payload.memory_type, payload.content, payload.importance
    else:
        memory = UserMemory(user_id=user.id, **payload.model_dump()); db.add(memory)
    db.commit(); db.refresh(memory)
    return {"code": 0, "message": "ok", "data": {"id": memory.id, "memory_type": memory.memory_type, "memory_key": memory.memory_key, "content": memory.content, "importance": memory.importance}}


@app.post("/api/v1/memories/extract")
async def extract_memories(payload: MemoryExtractIn, user: User = Depends(current_user), db: Session = Depends(db_session)):
    source = payload.content
    if payload.conversation_id is not None:
        owned(db, Conversation, payload.conversation_id, user.id)
        messages = db.scalars(select(Message).where(Message.conversation_id == payload.conversation_id, Message.user_id == user.id).order_by(Message.created_at.desc()).limit(10)).all()
        source = "\n".join(f"{message.role}: {message.content}" for message in reversed(messages))
    schema = MemoryExtractOutput.model_json_schema()
    try:
        generated = await get_llm_provider().structured_output(
            "从输入中抽取可长期保存的学习目标、学习偏好、薄弱知识领域或当前计划状态。禁止保存密码、Token、API Key、敏感信息或短期答题内容；没有合适内容时返回空数组。",
            schema,
            [source],
        )
        extracted = MemoryExtractOutput.model_validate(generated)
    except Exception as error:
        raise HTTPException(503, "AI_PROVIDER_ERROR") from error
    items = []
    for memory_data in extracted.memories:
        memory = db.scalar(select(UserMemory).where(UserMemory.user_id == user.id, UserMemory.memory_key == memory_data.memory_key))
        if memory:
            memory.memory_type, memory.content, memory.importance, memory.source = memory_data.memory_type, memory_data.content, memory_data.importance, "agent-memory-extract"
        else:
            memory = UserMemory(user_id=user.id, source="agent-memory-extract", **memory_data.model_dump())
            db.add(memory)
        db.flush()
        items.append({"id": memory.id, "memory_type": memory.memory_type, "memory_key": memory.memory_key, "content": memory.content, "importance": memory.importance})
    db.commit()
    return {"code": 0, "message": "ok", "data": {"items": items}}


@app.get("/api/v1/memories/relevant")
def relevant_memories(query: str = Query(min_length=1, max_length=200), user: User = Depends(current_user), db: Session = Depends(db_session)):
    query_tokens = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", query.lower()))
    now = datetime.utcnow()
    items = []
    for memory in db.scalars(select(UserMemory).where(UserMemory.user_id == user.id, (UserMemory.expires_at.is_(None) | (UserMemory.expires_at > now)))).all():
        memory_tokens = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", memory.content.lower()))
        score = len(query_tokens & memory_tokens)
        if score:
            items.append((score, memory))
    items.sort(key=lambda item: (item[0], item[1].importance, item[1].updated_at), reverse=True)
    return {"code": 0, "message": "ok", "data": {"items": [{"id": memory.id, "memory_type": memory.memory_type, "memory_key": memory.memory_key, "content": memory.content, "importance": memory.importance, "score": score} for score, memory in items[:10]]}}


@app.delete("/api/v1/memories/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)):
    memory = owned(db, UserMemory, memory_id, user.id); db.delete(memory); db.commit()
    return {"code": 0, "message": "ok", "data": {"deleted": True}}
