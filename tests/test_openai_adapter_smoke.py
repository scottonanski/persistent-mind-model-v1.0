# tests/test_openai_adapter_smoke.py
import os
import json
from pmm.llm.adapters.openai_chat import OpenAIChat


class _DummyResp:
    def __init__(self, json_obj, status=200):
        self._json = json_obj
        self.status_code = status
        self.text = json.dumps(json_obj)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP error")


def test_openai_adapter_generate_monkeypatched(monkeypatch):
    os.environ["OPENAI_API_KEY"] = "sk-test"
    dummy = {"choices": [{"message": {"content": "ok1"}}]}

    def fake_post(url, headers=None, data=None, timeout=None):
        return _DummyResp(dummy, status=200)

    monkeypatch.setattr("pmm.llm.adapters.openai_chat.requests.post", fake_post)

    adapter = OpenAIChat("gpt-4o-mini")
    out = adapter.generate([{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=16)
    assert out == "ok1"
