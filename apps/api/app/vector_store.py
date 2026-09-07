from __future__ import annotations

import math
import os
import uuid
from typing import Any

from .providers import dev_mode

_store: FakeVectorStore | QdrantVectorStore | None = None


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    norm = math.sqrt(sum(value * value for value in left) * sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / norm if norm else 0.0


class FakeVectorStore:
    def __init__(self):
        self.points: dict[str, dict[str, Any]] = {}

    def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension

    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.points[str(point_id)] = {"vector": vector, "payload": payload}

    def search(self, vector: list[float], user_id: int, knowledge_base_id: int, limit: int = 6, score_threshold: float = 0.0) -> list[dict[str, Any]]:
        hits = []
        for point_id, point in self.points.items():
            payload = point["payload"]
            if payload.get("user_id") != user_id or payload.get("knowledge_base_id") != knowledge_base_id:
                continue
            score = _cosine(vector, point["vector"])
            if score >= score_threshold:
                hits.append({"id": point_id, "score": score, "payload": payload})
        return sorted(hits, key=lambda item: item["score"], reverse=True)[:limit]

    def delete_by_document(self, user_id: int, document_id: int) -> None:
        self.points = {key: value for key, value in self.points.items() if value["payload"].get("user_id") != user_id or value["payload"].get("document_id") != document_id}

    def delete_by_kb(self, user_id: int, knowledge_base_id: int) -> None:
        self.points = {key: value for key, value in self.points.items() if value["payload"].get("user_id") != user_id or value["payload"].get("knowledge_base_id") != knowledge_base_id}

    def health(self) -> str:
        return "ok"


class QdrantVectorStore:
    def __init__(self):
        from qdrant_client import QdrantClient
        url = os.getenv("QDRANT_URL", "").strip()
        if not url:
            raise RuntimeError("QDRANT_URL_REQUIRED")
        self.client = QdrantClient(url=url, timeout=float(os.getenv("QDRANT_TIMEOUT", "5")))
        self.collection = os.getenv("QDRANT_COLLECTION", "study_chunks")

    def ensure_collection(self, dimension: int) -> None:
        from qdrant_client.models import Distance, VectorParams
        try:
            current = self.client.get_collection(self.collection)
            configured = current.config.params.vectors.size
            if configured != dimension:
                raise RuntimeError(f"QDRANT_DIMENSION_MISMATCH:{configured}!={dimension}")
        except Exception as error:
            if "DIMENSION_MISMATCH" in str(error):
                raise
            self.client.create_collection(self.collection, vectors_config=VectorParams(size=dimension, distance=Distance.COSINE))

    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct
        try:
            qdrant_id = str(uuid.UUID(str(point_id)))
        except ValueError:
            qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(point_id)))
        self.client.upsert(collection_name=self.collection, points=[PointStruct(id=qdrant_id, vector=vector, payload=payload)])

    def search(self, vector: list[float], user_id: int, knowledge_base_id: int, limit: int = 6, score_threshold: float = 0.0) -> list[dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        query_filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id)), FieldCondition(key="knowledge_base_id", match=MatchValue(value=knowledge_base_id))])
        result = self.client.query_points(collection_name=self.collection, query=vector, query_filter=query_filter, limit=limit, score_threshold=score_threshold).points
        return [{"id": str(item.id), "score": item.score, "payload": item.payload or {}} for item in result]

    def delete_by_document(self, user_id: int, document_id: int) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        self.client.delete(collection_name=self.collection, points_selector=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id)), FieldCondition(key="document_id", match=MatchValue(value=document_id))]))

    def delete_by_kb(self, user_id: int, knowledge_base_id: int) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        self.client.delete(collection_name=self.collection, points_selector=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id)), FieldCondition(key="knowledge_base_id", match=MatchValue(value=knowledge_base_id))]))

    def health(self) -> str:
        self.client.get_collections()
        return "ok"


def get_vector_store():
    global _store
    provider = os.getenv("VECTOR_PROVIDER", "fake").lower()
    if provider == "fake":
        if not dev_mode():
            raise RuntimeError("VECTOR_PROVIDER_FAKE_FORBIDDEN")
        if not isinstance(_store, FakeVectorStore):
            _store = FakeVectorStore()
        return _store
    if provider == "qdrant":
        if not isinstance(_store, QdrantVectorStore):
            _store = QdrantVectorStore()
        return _store
    raise RuntimeError("VECTOR_PROVIDER_UNSUPPORTED")
