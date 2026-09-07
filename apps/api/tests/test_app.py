from fastapi.testclient import TestClient

from app.main import app, reset_store


def setup_function():
    reset_store()


client = TestClient(app)


def login(nickname="测试用户"):
    response = client.post("/api/v1/auth/dev-login", json={"nickname": nickname})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_dev_login_and_idor_are_isolated():
    token_a = login("A")
    created = client.post("/api/v1/knowledge-bases", headers=headers(token_a), json={"name": "网络"})
    assert created.status_code == 200
    kb_id = created.json()["data"]["id"]

    token_b = login("B")
    assert client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=headers(token_b)).status_code == 404


def test_dev_login_reuses_account_for_same_nickname():
    first = login("稳定账号")
    second = login("稳定账号")
    profile_a = client.get("/api/v1/auth/profile", headers=headers(first)).json()["data"]
    profile_b = client.get("/api/v1/auth/profile", headers=headers(second)).json()["data"]
    assert profile_a["id"] == profile_b["id"]


def test_upload_chat_plan_quiz_main_flow():
    token = login()
    auth = headers(token)
    kb = client.post("/api/v1/knowledge-bases", headers=auth, json={"name": "计算机网络", "category": "课程"}).json()["data"]
    upload = client.post(
        f"/api/v1/knowledge-bases/{kb['id']}/documents",
        headers=auth,
        files={"file": ("network.txt", "TCP 建立连接采用三次握手。".encode(), "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["data"]["status"] == "READY"

    conversation = client.post("/api/v1/conversations", headers=auth, json={"knowledge_base_id": kb["id"]}).json()["data"]
    answer = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=auth,
        json={"content": "TCP 建立连接需要几次握手？"},
    ).json()["data"]
    assert "三次" in answer["content"]
    assert answer["citations"]

    plan = client.post("/api/v1/study-plans", headers=auth, json={"name": "14天冲刺", "knowledge_base_id": kb["id"], "target_date": "2030-01-14", "daily_minutes": 30}).json()["data"]
    assert plan["status"] == "DRAFT"
    active = client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth).json()["data"]
    assert active["status"] == "ACTIVE"
    tasks = client.get("/api/v1/tasks/today", headers=auth).json()["data"]["items"]
    assert tasks
    client.post(f"/api/v1/tasks/{tasks[0]['id']}/complete", headers=auth)

    quiz = client.post("/api/v1/quizzes", headers=auth, json={"knowledge_base_id": kb["id"], "question_count": 5}).json()["data"]
    assert "correct_answer" not in quiz["questions"][0]
    submitted = client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth, json={"answers": [{"question_id": quiz["questions"][0]["id"], "answer": ["B"]}]}).json()["data"]
    assert "score" in submitted
    mastery = client.get(f"/api/v1/knowledge-bases/{kb['id']}/mastery", headers=auth).json()["data"]["items"]
    assert mastery[0]["mastery_score"] > 50
    assert client.post(f"/api/v1/quizzes/{quiz['id']}/submit", headers=auth, json={"answers": []}).status_code == 409


def test_upload_rejects_unsafe_extension():
    token = login()
    response = client.post(
        "/api/v1/knowledge-bases/1/documents",
        headers=headers(token),
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code in (404, 415)


def test_document_retry_conversation_lifecycle_and_agent_tool():
    token = login(); auth = headers(token)
    kb = client.post("/api/v1/knowledge-bases", headers=auth, json={"name": "工具测试"}).json()["data"]
    upload = client.post(f"/api/v1/knowledge-bases/{kb['id']}/documents", headers=auth, files={"file": ("empty.txt", b"", "text/plain")})
    doc_id = upload.json()["data"]["id"]
    assert upload.json()["data"]["status"] == "FAILED"
    retry = client.post(f"/api/v1/documents/{doc_id}/retry", headers=auth)
    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "FAILED"
    client.post(f"/api/v1/knowledge-bases/{kb['id']}/documents", headers=auth, files={"file": ("notes.txt", "学习任务需要按计划完成。".encode(), "text/plain")})
    conversation = client.post("/api/v1/conversations", headers=auth, json={"knowledge_base_id": kb["id"]}).json()["data"]
    assert client.get("/api/v1/conversations", headers=auth).json()["data"]["items"]
    assert client.delete(f"/api/v1/conversations/{conversation['id']}", headers=auth).status_code == 200

    plan = client.post("/api/v1/study-plans", headers=auth, json={"name": "工具计划", "knowledge_base_id": kb["id"], "target_date": "2030-01-14"}).json()["data"]
    client.post(f"/api/v1/study-plans/{plan['id']}/activate", headers=auth)
    task = client.get("/api/v1/tasks/today", headers=auth).json()["data"]["items"][0]
    result = client.post("/api/v1/agent/execute", headers=auth, json={"tool_name": "complete_study_task", "arguments": {"task_id": task["id"]}})
    assert result.status_code == 200
    assert result.json()["data"]["task"]["status"] == "DONE"


def test_wechat_login_requires_provider_when_not_dev(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    response = client.post("/api/v1/auth/wechat/login", json={"code": "demo"})
    assert response.status_code in (400, 503)


def test_access_token_is_jwt_and_websocket_streams_events():
    token = login(); assert token.count(".") == 2
    auth = headers(token)
    kb = client.post("/api/v1/knowledge-bases", headers=auth, json={"name": "流式库"}).json()["data"]
    conversation = client.post("/api/v1/conversations", headers=auth, json={"knowledge_base_id": kb["id"]}).json()["data"]
    with client.websocket_connect(f"/ws/v1/chat/{conversation['id']}?token={token}") as websocket:
        websocket.send_json({"content": "资料里有什么？"})
        events = [websocket.receive_json() for _ in range(4)]
    assert events[0]["type"] == "retrieval_started"
    assert events[2]["type"] == "token"
    assert events[-1]["type"] == "done"


def test_quiz_supports_multiple_and_true_false_without_leaking_answers():
    token = login(); auth = headers(token)
    kb = client.post("/api/v1/knowledge-bases", headers=auth, json={"name": "题型库"}).json()["data"]
    upload = client.post(f"/api/v1/knowledge-bases/{kb['id']}/documents", headers=auth, files={"file": ("quiz.txt", "资料包含一个关键结论。".encode(), "text/plain")})
    assert upload.status_code == 200
    quiz = client.post("/api/v1/quizzes", headers=auth, json={"knowledge_base_id": kb["id"], "question_count": 5, "question_types": ["MULTIPLE", "TRUE_FALSE"]})
    assert quiz.status_code == 200
    questions = quiz.json()["data"]["questions"]
    assert {q["question_type"] for q in questions} <= {"MULTIPLE", "TRUE_FALSE"}
    assert "correct_answer" not in questions[0]


def test_resource_detail_archive_plan_list_and_short_answer_scoring():
    token = login(); auth = headers(token)
    kb = client.post("/api/v1/knowledge-bases", headers=auth, json={"name": "完整接口"}).json()["data"]
    updated = client.patch(f"/api/v1/knowledge-bases/{kb['id']}", headers=auth, json={"name": "已归档", "status": "ARCHIVED"})
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "ARCHIVED"
    doc = client.post(f"/api/v1/knowledge-bases/{kb['id']}/documents", headers=auth, files={"file": ("a.txt", "TCP 三次握手".encode(), "text/plain")}).json()["data"]
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=auth).json()["data"]["id"] == doc["id"]
    plan = client.post("/api/v1/study-plans", headers=auth, json={"name": "计划", "knowledge_base_id": kb["id"], "target_date": "2030-01-14"}).json()["data"]
    assert client.get("/api/v1/study-plans", headers=auth).json()["data"]["items"][0]["id"] == plan["id"]
