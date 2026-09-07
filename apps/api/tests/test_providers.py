import asyncio

from app.providers import FakeEmbeddingProvider, FakeLLMProvider, get_embedding_provider, get_llm_provider


def test_fake_providers_are_deterministic_and_configurable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)
    assert asyncio.run(provider.chat("问题", ["资料片段"]))["citations"] == [0]
    vectors = asyncio.run(FakeEmbeddingProvider().embed_documents(["abc", "abc"]))
    assert vectors[0] == vectors[1]


def test_explicit_test_providers_are_allowed_only_for_production_like_runs(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("TEST_LLM_PROVIDER", "true")
    monkeypatch.setenv("LLM_PROVIDER", "test")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "test")
    assert get_llm_provider().health() == "test-provider"
    assert get_embedding_provider().health() == "test-provider"
