from __future__ import annotations

import os
from typing import Any


class FakeVectorStore:
    def __init__(self): self.points: dict[str, dict[str, Any]] = {}
    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None: self.points[point_id] = {"vector": vector, "payload": payload}
    def delete_by_kb(self, user_id: int, knowledge_base_id: int) -> None: self.points = {key: value for key, value in self.points.items() if value["payload"].get("user_id") != user_id or value["payload"].get("knowledge_base_id") != knowledge_base_id}


class QdrantVectorStore:
    def __init__(self):
        from qdrant_client import QdrantClient
        self.client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333")); self.collection = os.getenv("QDRANT_COLLECTION", "study_chunks")
    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct
        self.client.upsert(collection_name=self.collection, points=[PointStruct(id=point_id, vector=vector, payload=payload)])
    def delete_by_kb(self, user_id: int, knowledge_base_id: int) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        self.client.delete(collection_name=self.collection, points_selector=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id)), FieldCondition(key="knowledge_base_id", match=MatchValue(value=knowledge_base_id))]))


def get_vector_store():
    if os.getenv("VECTOR_PROVIDER", "fake").lower() == "qdrant":
        try: return QdrantVectorStore()
        except Exception: pass
    return FakeVectorStore()
