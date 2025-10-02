import types

from pmm.cli import introspect as mod


def test_cli_writes_single_introspection_event(monkeypatch, capsys, tmp_path):
    # Stub LLMFactory.from_config -> returns object with .chat.generate
    class _StubChat:
        def generate(self, messages, temperature=0.0, max_tokens=256, **kw):
            return "Introspection summary."  # already clean for simplicity

    class _StubFactory:
        @staticmethod
        def from_config(cfg):
            return types.SimpleNamespace(chat=_StubChat())

    monkeypatch.setattr(mod, "LLMFactory", _StubFactory)

    # Stub EventLog to capture append writes
    appended = []

    class _FakeEventLog:
        def __init__(self, path):
            self.path = path

        def append(self, *, kind: str, content: str, meta: dict):
            appended.append({"kind": kind, "content": content, "meta": dict(meta)})
            return len(appended)

    monkeypatch.setattr(mod, "EventLog", _FakeEventLog)

    rc = mod.main(
        [
            "--topic",
            "reflection-order",
            "--scope",
            "runtime",
            "--path",
            str(tmp_path / "db.sqlite"),
        ]
    )
    assert rc == 0

    # Exactly one append with the expected shape
    assert len(appended) == 1
    ev = appended[0]
    assert ev["kind"] == "introspection_report"
    assert ev["meta"]["topic"] == "reflection-order"
    assert ev["meta"]["scope"] == "runtime"
    assert ev["content"] == "Introspection summary."

    # Stdout prints the summary
    out = capsys.readouterr().out.strip()
    assert out == "Introspection summary."
