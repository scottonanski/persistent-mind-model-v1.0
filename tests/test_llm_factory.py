from pytest import raises

from pmm.llm.factory import LLMFactory, LLMConfig


def test_openai_bundle_shapes():
    cfg = LLMConfig(
        provider="openai",
        model="gpt-4o",
        embed_provider="openai",
        embed_model="text-embedding-3-small",
    )
    bundle = LLMFactory.from_config(cfg)

    assert hasattr(bundle.chat, "generate")
    assert bundle.embed is not None and hasattr(bundle.embed, "embed")

    from pmm.llm.adapters.openai_chat import OpenAIChat
    from pmm.llm.adapters.openai_embed import OpenAIEmbed

    assert isinstance(bundle.chat, OpenAIChat)
    assert isinstance(bundle.embed, OpenAIEmbed)


def test_ollama_bundle_shapes():
    cfg = LLMConfig(provider="ollama", model="llama3:instruct", embed_provider=None, embed_model=None)
    bundle = LLMFactory.from_config(cfg)

    assert hasattr(bundle.chat, "generate")
    assert bundle.embed is None

    from pmm.llm.adapters.ollama_chat import OllamaChat

    assert isinstance(bundle.chat, OllamaChat)


def test_unknown_provider_raises():
    cfg = LLMConfig(provider="mysteryai", model="x")
    with raises(ValueError):
        LLMFactory.from_config(cfg)


def test_unknown_embed_provider_raises():
    cfg = LLMConfig(provider="openai", model="gpt-4o", embed_provider="weird", embed_model="x")
    with raises(ValueError):
        LLMFactory.from_config(cfg)

