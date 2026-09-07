from datetime import date, timedelta

import pytest

from app.main import DocumentChunk, SessionLocal, StudyTask, app, reset_store
from app.providers import get_embedding_provider, get_llm_provider
from app.storage import LocalStorage
from app.vector_store import FakeVectorStore
from fastapi.testclient import TestClient


client = TestClient(app)


def setup_function():
    reset_store()


def login(nickname: str):
    response = client.post("/api/v1/auth/dev-login", json={"nickname": nickname})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def make_kb(token: str, name: str = "资料库"):
    return client.post("/api/v1/knowledge-bases", headers=auth(token), json={"name": name}).json()["data"]


def upload(token: str, kb_id: int, content: str, name: str = "notes.txt"):
    return client.post(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=auth(token), files={"file": (name, content.encode(), "text/plain")}).json()["data"]


def test_rag_retrieval_rejects_no_material_and_low_similarity():
    token = login("rag")
    kb = make_kb(token)
    conversation = client.post("/api/v1/conversations", headers=auth(token), json={"knowledge_base_id": kb["id"]}).json()["data"]
    empty = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token), json={"content": "TCP 握手"}).json()["data"]
    assert not empty["citations"]
    assert "资料不足" in empty["content"]
    upload(token, kb["id"], "量子纠缠是量子力学现象。")
    low = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token), json={"content": "TCP 三次握手"}).json()["data"]
    assert not low["citations"]


def test_rag_filter_blocks_cross_user_points():
    token_a, token_b = login("A"), login("B")
    kb_a, kb_b = make_kb(token_a, "A库"), make_kb(token_b, "B库")
    upload(token_a, kb_a["id"], "只有用户 A 能看到的机密学习资料。")
    conversation = client.post("/api/v1/conversations", headers=auth(token_b), json={"knowledge_base_id": kb_b["id"]}).json()["data"]
    result = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token_b), json={"content": "机密学习资料"}).json()["data"]
    assert not result["citations"]


def test_plan_and_quiz_reject_knowledge_base_without_material():
    token = login("empty-ai")
    kb = make_kb(token)
    plan = client.post("/api/v1/study-plans", headers=auth(token), json={"name": "空资料计划", "knowledge_base_id": kb["id"], "target_date": (date.today() + timedelta(days=1)).isoformat()})
    quiz = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5})
    assert plan.status_code == quiz.status_code == 422
    assert plan.json()["detail"] == quiz.json()["detail"] == "KNOWLEDGE_BASE_NO_RELIABLE_MATERIAL"


def test_generated_quiz_content_and_citation_are_persisted(monkeypatch):
    class Provider:
        async def structured_output(self, instruction, schema, contexts):
            return {"questions": [{"question_type": "SINGLE", "question": "资料的核心结论是什么？", "options": ["答案文本", "干扰项"], "correct_answer": ["答案文本"], "explanation": "资料证据支持答案。", "reference_answer": "答案文本", "scoring_points": ["答案文本"], "evidence": "不可信的模型自报证据", "source_chunk_ids": [999], "difficulty": "medium"}]}

    from app import main
    monkeypatch.setattr(main, "get_llm_provider", lambda: Provider())
    token = login("generated-quiz")
    kb = make_kb(token)
    upload(token, kb["id"], "资料真实证据文本。")
    quiz = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5}).json()["data"]
    assert quiz["questions"][0]["options"] == ["答案文本", "干扰项"]
    submitted = client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth(token), json={"answers": [{"question_id": quiz["questions"][0]["id"], "answer": ["A"]}]})
    assert submitted.status_code == 200
    revealed = submitted.json()["data"]["quiz"]["questions"][0]
    assert revealed["correct_answer"] == ["A"]
    assert revealed["evidence"] == "资料真实证据文本。"


def test_chat_history_preserves_citations():
    token = login("chat-history")
    kb = make_kb(token)
    upload(token, kb["id"], "历史消息的真实资料证据。")
    conversation = client.post("/api/v1/conversations", headers=auth(token), json={"knowledge_base_id": kb["id"]}).json()["data"]
    response = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token), json={"content": "真实资料证据是什么？"})
    assert response.status_code == 200 and response.json()["data"]["citations"]
    history = client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token)).json()["data"]["items"]
    assert history[-1]["citations"]


def test_document_delete_failure_is_retryable(monkeypatch):
    token = login("cleanup")
    kb = make_kb(token)
    document = upload(token, kb["id"], "需要保留的资料。")

    class BrokenStorage:
        def delete(self, key):
            raise OSError("storage unavailable")

    from app import main
    monkeypatch.setattr(main, "get_storage", lambda: BrokenStorage())
    response = client.delete(f"/api/v1/documents/{document['id']}", headers=auth(token))
    assert response.status_code == 503
    assert client.get(f"/api/v1/documents/{document['id']}", headers=auth(token)).status_code == 200


def test_rebuild_ready_document_reprocesses_index():
    token = login("rebuild")
    kb = make_kb(token)
    document = upload(token, kb["id"], "可重建索引的真实资料。")
    response = client.post(f"/api/v1/documents/{document['id']}/rebuild", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "READY"


def test_short_answer_uses_rubric_scoring():
    token = login("short")
    kb = make_kb(token)
    upload(token, kb["id"], "简答题需要覆盖核心概念和关键结论。")
    quiz = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5, "question_types": ["SHORT"]}).json()["data"]
    question = quiz["questions"][0]
    response = client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth(token), json={"answers": [{"question_id": question["id"], "answer": ["核心概念"]}]})
    assert response.status_code == 200
    answer = response.json()["data"]["quiz"]["questions"][0]
    assert answer["ai_feedback"] and 0 <= answer["score"] <= answer["score_value"]


def test_production_readiness_rejects_fake_dependencies(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")
    monkeypatch.setenv("VECTOR_PROVIDER", "fake")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_memory_retrieve_and_delete_are_user_scoped():
    token_a, token_b = login("memory-a"), login("memory-b")
    created = client.post("/api/v1/memories", headers=auth(token_a), json={"memory_type": "goal", "memory_key": "exam", "content": "准备数据库考试", "importance": 5}).json()["data"]
    relevant = client.get("/api/v1/memories/relevant", headers=auth(token_a), params={"query": "数据库"}).json()["data"]["items"]
    assert relevant and relevant[0]["id"] == created["id"]
    assert client.get("/api/v1/memories", headers=auth(token_b)).json()["data"]["items"] == []
    assert client.delete(f"/api/v1/memories/{created['id']}", headers=auth(token_b)).status_code == 404


def test_plan_activation_is_idempotent_and_today_is_date_filtered():
    token = login("plan")
    kb = make_kb(token)
    upload(token, kb["id"], "计划资料包含需要掌握的核心知识点。")
    plan = client.post("/api/v1/study-plans", headers=auth(token), json={"name": "计划", "knowledge_base_id": kb["id"], "target_date": (date.today() + timedelta(days=3)).isoformat(), "daily_minutes": 30}).json()["data"]
    first = client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth(token)).json()["data"]
    second = client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth(token)).json()["data"]
    assert first["status"] == second["status"] == "ACTIVE"
    with SessionLocal() as db:
        count = len(db.query(StudyTask).filter(StudyTask.study_plan_id == plan["id"]).all())
        assert count > 0
        old = db.query(StudyTask).filter(StudyTask.study_plan_id == plan["id"]).first()
        old.scheduled_date = date.today() - timedelta(days=1)
        db.commit()
    today = client.get("/api/v1/tasks/today", headers=auth(token)).json()["data"]["items"]
    assert all(item["scheduled_date"] == date.today().isoformat() for item in today)


def test_incomplete_quiz_creates_answer_for_every_question_and_second_submit_conflicts():
    token = login("quiz")
    kb = make_kb(token)
    upload(token, kb["id"], "学习资料包含一个明确的核心结论。")
    quiz = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5}).json()["data"]
    first = client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth(token), json={"answers": []})
    assert first.status_code == 200
    with SessionLocal() as db:
        assert db.query(DocumentChunk).count() > 0
        from app.main import QuizAnswer, WrongQuestion
        assert db.query(QuizAnswer).filter(QuizAnswer.quiz_id == quiz["id"]).count() == 5
        assert db.query(WrongQuestion).count() == 5
    assert client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth(token), json={"answers": []}).status_code == 409


def test_agent_allowlist_and_idor():
    token_a, token_b = login("agent-a"), login("agent-b")
    kb = make_kb(token_a)
    upload(token_a, kb["id"], "Agent 任务资料。")
    plan = client.post("/api/v1/study-plans", headers=auth(token_a), json={"name": "计划", "knowledge_base_id": kb["id"], "target_date": (date.today() + timedelta(days=1)).isoformat()}).json()["data"]
    client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth(token_a))
    task_id = client.get("/api/v1/tasks/today", headers=auth(token_a)).json()["data"]["items"][0]["id"]
    assert client.post("/api/v1/agent/execute", headers=auth(token_b), json={"tool_name": "complete_study_task", "arguments": {"task_id": task_id}}).status_code == 404
    assert client.post("/api/v1/agent/execute", headers=auth(token_a), json={"tool_name": "unknown", "arguments": {}}).status_code == 400


def test_production_providers_fail_fast(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    with pytest.raises(RuntimeError, match="FAKE_FORBIDDEN"):
        get_llm_provider()
    with pytest.raises(RuntimeError, match="FAKE_FORBIDDEN"):
        get_embedding_provider()


def test_local_storage_and_vector_cleanup(tmp_path):
    storage = LocalStorage(tmp_path)
    key = storage.put(1, 2, "a.txt", b"data")
    storage.delete(key)
    with pytest.raises(FileNotFoundError):
        storage.get(key)
    vector = FakeVectorStore()
    vector.upsert("1", [1.0, 0.0], {"user_id": 1, "knowledge_base_id": 2, "document_id": 3})
    assert vector.search([1.0, 0.0], 1, 2)
    vector.delete_by_document(1, 3)
    assert not vector.search([1.0, 0.0], 1, 2)
    with pytest.raises(ValueError, match="STORAGE_KEY_INVALID"):
        storage.get("../outside")


def test_quiz_rejects_unknown_question_type_instead_of_downgrading():
    token = login("quiz-type")
    kb = make_kb(token)
    upload(token, kb["id"], "题型校验资料。")
    response = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5, "question_types": ["ESSAY"]})
    assert response.status_code == 422
    assert response.json()["detail"] == "QUIZ_QUESTION_TYPE_INVALID"


def test_deleted_document_can_be_reuploaded_and_cannot_be_retrieved(monkeypatch):
    token = login("reupload")
    kb = make_kb(token)
    first = upload(token, kb["id"], "可再次上传的资料。")
    assert client.delete(f"/api/v1/documents/{first['id']}", headers=auth(token)).status_code == 200
    second = upload(token, kb["id"], "可再次上传的资料。")
    assert second["id"] != first["id"]
    conversation = client.post("/api/v1/conversations", headers=auth(token), json={"knowledge_base_id": kb["id"]}).json()["data"]
    result = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token), json={"content": "再次上传的资料"}).json()["data"]
    assert result["citations"] and all(item["document_id"] == second["id"] for item in result["citations"])


def test_generated_plan_schedule_drives_activated_tasks(monkeypatch):
    class Provider:
        async def structured_output(self, instruction, schema, contexts):
            return {"plan_name": "AI 计划", "summary": "按资料拆分", "days": [{"date": date.today().isoformat(), "goal": "先学核心", "estimated_minutes": 25, "tasks": [{"type": "READ", "title": "阅读核心资料", "estimated_minutes": 25}]}]}

    from app import main
    monkeypatch.setattr(main, "get_llm_provider", lambda: Provider())
    token = login("generated-plan")
    kb = make_kb(token)
    upload(token, kb["id"], "计划的核心资料。")
    plan = client.post("/api/v1/study-plans", headers=auth(token), json={"name": "草案", "knowledge_base_id": kb["id"], "target_date": (date.today() + timedelta(days=2)).isoformat()}).json()["data"]
    assert plan["schedule"][0]["tasks"][0]["title"] == "阅读核心资料"
    client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth(token))
    tasks = client.get("/api/v1/tasks/today", headers=auth(token)).json()["data"]["items"]
    assert any(task["title"] == "阅读核心资料" for task in tasks)


def test_production_startup_requires_redis_and_qdrant_urls(monkeypatch):
    from app.main import validate_production_startup
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("JWT_SECRET", "a-valid-production-secret-with-enough-entropy-123456")
    monkeypatch.setenv("CORS_ORIGINS", "https://study.example")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://user:pass@db/study_agent")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("QDRANT_URL", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL_REQUIRED"):
        validate_production_startup()


def test_production_startup_rejects_wildcard_cors(monkeypatch):
    from app.main import validate_production_startup

    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("JWT_SECRET", "a-valid-production-secret-with-enough-entropy-123456")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS_WILDCARD"):
        validate_production_startup()


def test_quiz_submission_failure_releases_claim(monkeypatch):
    from app import main

    token = login("quiz-failure")
    kb = make_kb(token)
    upload(token, kb["id"], "提交阶段异常恢复资料。")
    quiz = client.post("/api/v1/quizzes", headers=auth(token), json={"knowledge_base_id": kb["id"], "question_count": 5}).json()["data"]
    monkeypatch.setattr(main, "refresh_plan_progress", lambda *args: (_ for _ in ()).throw(RuntimeError("progress unavailable")))
    failed = client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth(token), json={"answers": []})
    assert failed.status_code == 503
    assert client.get(f"/api/v1/quizzes/{quiz['id']}", headers=auth(token)).json()["data"]["status"] == "ACTIVE"


def test_invalid_jwt_payload_returns_401():
    import jwt
    token = jwt.encode({"user_id": {}}, "dev-only-change-me-please-32-chars", algorithm="HS256")
    assert client.get("/api/v1/auth/profile", headers=auth(token)).status_code == 401


def test_account_deletion_cleans_user_data_and_storage():
    from app.main import Conversation, Document, KnowledgeBase, Message, User, UserMemory

    token = login("delete-account")
    user_id = client.get("/api/v1/auth/profile", headers=auth(token)).json()["data"]["id"]
    kb = make_kb(token)
    document = upload(token, kb["id"], "账号删除后不应保留的资料。")
    conversation = client.post("/api/v1/conversations", headers=auth(token), json={"knowledge_base_id": kb["id"]}).json()["data"]
    client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=auth(token), json={"content": "资料是什么？"})
    client.post("/api/v1/memories", headers=auth(token), json={"memory_type": "goal", "memory_key": "delete", "content": "待删除"})

    assert client.delete("/api/v1/auth/account", headers=auth(token)).status_code == 200
    assert client.get("/api/v1/auth/profile", headers=auth(token)).status_code == 401
    with SessionLocal() as db:
        assert db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user_id).count() == 0
        assert db.query(Document).filter(Document.id == document["id"]).count() == 0
        assert db.query(Conversation).filter(Conversation.id == conversation["id"]).count() == 0
        assert db.query(Message).filter(Message.conversation_id == conversation["id"]).count() == 0
        assert db.query(UserMemory).filter(UserMemory.memory_key == "delete").count() == 0
        assert db.query(User).filter(User.id == user_id, User.status == "DISABLED", User.nickname == "已注销用户").count() == 1


def test_memory_extract_uses_structured_provider_and_user_scope(monkeypatch):
    class Provider:
        async def structured_output(self, instruction, schema, contexts):
            return {"memories": [{"memory_type": "preference", "memory_key": "study_style", "content": "偏好晚间学习", "importance": 3}]}

    from app import main

    monkeypatch.setattr(main, "get_llm_provider", lambda: Provider())
    token = login("memory-extract")
    response = client.post("/api/v1/memories/extract", headers=auth(token), json={"content": "我偏好晚间学习。"})
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["memory_key"] == "study_style"
    other = login("memory-extract-other")
    assert client.get("/api/v1/memories", headers=auth(other)).json()["data"]["items"] == []
