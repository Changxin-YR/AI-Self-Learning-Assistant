from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import boto3
import httpx
import pymysql
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "docker-compose.yml"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def provision_minio_bucket(port: int, bucket: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{port}",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="change-me",
        region_name="us-east-1",
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            client.head_bucket(Bucket=bucket)
            return
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchBucket"}:
                client.create_bucket(Bucket=bucket)
                return
            time.sleep(1)
        except Exception:
            time.sleep(1)
    raise RuntimeError("MinIO bucket provisioning timeout")


def required_files() -> None:
    for path in (COMPOSE, ROOT / "apps" / "api" / "alembic", ROOT / "apps" / "wechat-miniprogram"):
        if not path.exists():
            raise SystemExit(f"missing production-like dependency: {path}")


def run() -> int:
    parser = argparse.ArgumentParser(description="Run StudyAgent against real Docker dependencies with explicit test providers.")
    parser.add_argument("--check", action="store_true", help="validate production-like settings without starting containers")
    parser.add_argument("--keep", action="store_true", help="keep containers running after the smoke chain")
    args = parser.parse_args()
    required_files()
    env = os.environ.copy()
    api_port = free_port()
    mysql_port = free_port()
    minio_port = free_port()
    qdrant_port = free_port()
    env.update({
        "APP_ENV": "production",
        "DEV_MODE": "false",
        "JWT_SECRET": "production-like-e2e-secret-with-entropy-123456",
        "CORS_ORIGINS": "https://e2e.example.invalid",
        "LLM_PROVIDER": "test",
        "EMBEDDING_PROVIDER": "test",
        "TEST_LLM_PROVIDER": "true",
        "CONTENT_SAFETY_PROVIDER": "test_rules",
        "TEST_LOGIN_PROVIDER": "true",
        # Keep the harness on the dependency-supported runtime so locked native
        # wheels (notably pydantic-core) are available without a compiler.
        "E2E_BASE_IMAGE": "python:3.12-slim",
        "DATABASE_URL": "mysql+pymysql://study_agent:change-me@mysql:3306/study_agent",
        "REDIS_URL": "redis://redis:6379/0",
        "S3_ENDPOINT": "http://minio:9000",
        "S3_ACCESS_KEY": "minioadmin",
        "S3_SECRET_KEY": "change-me",
        "S3_BUCKET": "study-agent",
        "QDRANT_URL": "http://qdrant:6333",
        "MYSQL_HOST_PORT": str(mysql_port),
        "REDIS_HOST_PORT": str(free_port()),
        "QDRANT_HOST_PORT": str(qdrant_port),
        "MINIO_HOST_PORT": str(minio_port),
        "MINIO_CONSOLE_PORT": str(free_port()),
        "API_HOST_PORT": str(api_port),
    })
    if args.check:
        print("production-like configuration validated: DEV_MODE=false, test providers explicit, real MySQL/Redis/MinIO/Qdrant services declared")
        return 0
    compose = ["docker", "compose", "-p", "study-agent-e2e", "-f", str(COMPOSE), "up", "--build", "-d"]
    try:
        subprocess.run(["docker", "compose", "-p", "study-agent-e2e", "-f", str(COMPOSE), "down", "--remove-orphans"], cwd=ROOT, env=env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(compose, cwd=ROOT, env=env, check=True)
        provision_minio_bucket(minio_port, "study-agent")
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                response = httpx.get(f"http://127.0.0.1:{api_port}/health", timeout=3)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("API health timeout")
        ready = httpx.get(f"http://127.0.0.1:{api_port}/ready", timeout=10)
        if ready.status_code != 200:
            raise RuntimeError(f"production readiness failed: {ready.text[:300]}")
        client = httpx.Client(base_url=f"http://127.0.0.1:{api_port}/api/v1", timeout=20)
        login = client.post("/auth/wechat/login", json={"code": "production-like-e2e"})
        login.raise_for_status()
        login_data = login.json()["data"]
        token = login_data["access_token"]
        user_id = int(login_data["user"]["id"])
        headers = {"Authorization": f"Bearer {token}"}
        kb = client.post("/knowledge-bases", headers=headers, json={"name": "E2E 资料"}).json()["data"]
        upload = client.post(f"/knowledge-bases/{kb['id']}/documents", headers=headers, files={"file": ("e2e.txt", "TCP 建立连接采用三次握手。".encode(), "text/plain")})
        upload.raise_for_status()
        document_id = upload.json()["data"]["id"]
        storage_client = boto3.client("s3", endpoint_url=f"http://127.0.0.1:{minio_port}", aws_access_key_id="minioadmin", aws_secret_access_key="change-me", region_name="us-east-1")
        prefix = f"users/{user_id}/knowledge-bases/{kb['id']}/documents/"
        if not storage_client.list_objects_v2(Bucket="study-agent", Prefix=prefix).get("Contents", []):
            raise RuntimeError("MinIO object missing after upload")
        for _ in range(60):
            status = client.get(f"/documents/{document_id}/status", headers=headers).json()["data"]["status"]
            if status == "READY":
                break
            if status == "FAILED":
                raise RuntimeError("document worker failed")
            time.sleep(2)
        else:
            raise RuntimeError("document READY timeout")
        conversation = client.post("/conversations", headers=headers, json={"knowledge_base_id": kb["id"]}).json()["data"]
        answer = client.post(f"/conversations/{conversation['id']}/messages", headers=headers, json={"content": "TCP 三次握手"}).json()["data"]
        if not answer["citations"]:
            raise RuntimeError("RAG citation missing")
        plan = client.post("/study-plans", headers=headers, json={"name": "E2E 计划", "knowledge_base_id": kb["id"], "target_date": "2030-01-14"}).json()["data"]
        client.post(f"/study-plans/{plan['id']}/activate", headers=headers).raise_for_status()
        quiz_response = client.post("/quizzes", headers=headers, json={"knowledge_base_id": kb["id"], "question_count": 5})
        quiz_response.raise_for_status()
        quiz = quiz_response.json()["data"]
        submitted = client.post(f"/quizzes/{quiz['id']}/submit", headers=headers, json={"answers": []})
        submitted.raise_for_status()
        result = submitted.json()["data"]
        if result["correct_rate"] != 0 or len(result["quiz"]["questions"]) != quiz["question_count"]:
            raise RuntimeError("quiz grading did not record unanswered questions")
        mastery = client.get(f"/knowledge-bases/{kb['id']}/mastery", headers=headers)
        mastery.raise_for_status()
        if not mastery.json()["data"]["items"]:
            raise RuntimeError("mastery record missing after quiz")
        db = pymysql.connect(host="127.0.0.1", port=mysql_port, user="study_agent", password="change-me", database="study_agent")
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM wrong_questions WHERE user_id=%s AND knowledge_base_id=%s", (user_id, kb["id"]))
                if cursor.fetchone()[0] < quiz["question_count"]:
                    raise RuntimeError("wrong questions were not persisted")
        finally:
            db.close()
        tools = client.get("/agent/tools", headers=headers).json()["data"]["tools"]
        expected_tools = {"get_today_tasks", "complete_study_task", "get_learning_progress", "get_knowledge_base_summary"}
        if {item["name"] for item in tools} != expected_tools:
            raise RuntimeError("agent tool allowlist incomplete")
        today = client.get("/tasks/today", headers=headers).json()["data"]["items"]
        if today:
            completed = client.post("/agent/execute", headers=headers, json={"tool_name": "complete_study_task", "arguments": {"task_id": today[0]["id"]}})
            completed.raise_for_status()
        for tool_name, arguments in (("get_today_tasks", {}), ("get_learning_progress", {}), ("get_knowledge_base_summary", {"knowledge_base_id": kb["id"]})):
            client.post("/agent/execute", headers=headers, json={"tool_name": tool_name, "arguments": arguments}).raise_for_status()
        client.post("/memories", headers=headers, json={"memory_type": "goal", "memory_key": "e2e", "content": "完成 E2E"}).raise_for_status()
        client.delete(f"/documents/{document_id}", headers=headers).raise_for_status()
        for _ in range(60):
            jobs = [item for item in client.get("/cleanup-jobs", headers=headers).json()["data"]["items"] if item["resource_id"] == document_id]
            if jobs and all(item["status"] == "SUCCEEDED" for item in jobs):
                break
            if any(item["status"] == "FAILED" for item in jobs):
                raise RuntimeError(f"cleanup failed: {jobs}")
            time.sleep(1)
        else:
            raise RuntimeError("cleanup job timeout")
        if storage_client.list_objects_v2(Bucket="study-agent", Prefix=prefix).get("Contents", []):
            raise RuntimeError("MinIO object remained after cleanup")
        qdrant_points = httpx.post(f"http://127.0.0.1:{qdrant_port}/collections/study_chunks/points/scroll", json={"limit": 10, "filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}}).json().get("result", {}).get("points", [])
        if qdrant_points:
            raise RuntimeError("Qdrant points remained after cleanup")
        after_delete = client.post(f"/conversations/{conversation['id']}/messages", headers=headers, json={"content": "TCP 三次握手"}).json()["data"]
        if after_delete["citations"]:
            raise RuntimeError("deleted document still returned as RAG citation")
        print("production-like E2E passed: login -> KB -> MinIO/Celery -> READY -> Qdrant RAG citation -> plan/tasks -> quiz submit -> WrongQuestion/Mastery -> Agent -> memory -> cleanup -> storage/vector empty")
        client.close()
        return 0
    finally:
        if not args.keep:
            subprocess.run(["docker", "compose", "-p", "study-agent-e2e", "-f", str(COMPOSE), "down"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    sys.exit(run())
