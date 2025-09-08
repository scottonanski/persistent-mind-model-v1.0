# tests/test_openai_adapter_smoke.py
import os
import json
from pmm.llm.adapters.openai_chat import OpenAIChat


class _DummyResp:
    def __init__(self, obj):
        self._bytes = json.dumps(obj).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_openai_adapter_generate_monkeypatched(monkeypatch):
    os.environ["OPENAI_API_KEY"] = "sk-test"
    dummy = {"choices": [{"message": {"content": "ok1"}}]}

    def fake_urlopen(req, timeout=None):
        return _DummyResp(dummy)

    # Patch where it's used
    monkeypatch.setattr("pmm.llm.adapters.openai_chat.urlopen", fake_urlopen)

    adapter = OpenAIChat("gpt-4o-mini")
    out = adapter.generate([{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=16)
    assert out == "ok1"
