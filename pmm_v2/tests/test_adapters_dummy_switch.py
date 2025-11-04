from __future__ import annotations

from pmm_v2.adapters.factory import LLMFactory
from pmm_v2.adapters.dummy_adapter import DummyAdapter


def test_factory_returns_dummy_by_default():
    adapter = LLMFactory().get()
    assert isinstance(adapter, DummyAdapter)
    out = adapter.generate_reply("sys", "hi")
    assert out.startswith("Echo: hi")


def test_import_openai_and_ollama_adapters():
    # Import but do not instantiate network calls
    from pmm_v2.adapters.openai_adapter import OpenAIAdapter  # noqa: F401
    from pmm_v2.adapters.ollama_adapter import OllamaAdapter  # noqa: F401

