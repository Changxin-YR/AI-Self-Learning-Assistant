import asyncio

from app.providers import FakeEmbeddingProvider, FakeLLMProvider, get_llm_provider


def test_fake_providers_are_deterministic_and_configurable(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)
    assert asyncio.run(provider.chat("问题", ["资料片段"]))["citations"] == [0]
    vectors = asyncio.run(FakeEmbeddingProvider().embed_documents(["abc", "abc"]))
    assert vectors[0] == vectors[1]
