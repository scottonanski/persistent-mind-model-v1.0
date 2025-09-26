import importlib


def test_limits_ignore_env_gates(monkeypatch):
    # Set env vars that used to influence behavior
    monkeypatch.setenv("PMM_MAX_CHAT_PER_TICK", "99")
    monkeypatch.setenv("PMM_MAX_EMBED_PER_TICK", "123")

    # Reload the module to ensure constants are evaluated fresh
    limits = importlib.import_module("pmm.llm.limits")
    importlib.reload(limits)

    assert limits.MAX_CHAT_CALLS_PER_TICK == 4
    assert limits.MAX_EMBED_CALLS_PER_TICK == 20
