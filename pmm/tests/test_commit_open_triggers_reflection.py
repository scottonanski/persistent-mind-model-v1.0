from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class CommitAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "OK\nCOMMIT: do the thing"


def test_commit_open_triggers_reflection():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=CommitAdapter(), autonomy=False)
    events = loop.run_turn("hello")
    kinds = [
        e["kind"]
        for e in events
        if e["kind"]
        not in {
            "autonomy_rule_table",
            "autonomy_stimulus",
            "rsm_update",
            "config",
            "embedding_add",
        }
    ]
    assert kinds[0] == "user_message"
    assert kinds[1] == "assistant_message"
    assert "commitment_open" in kinds
    assert kinds[-2] == "commitment_open"
    assert kinds[-1] == "reflection"
    last_reflection = [e for e in events if e["kind"] == "reflection"][-1]
    assert last_reflection["meta"].get("source") is None
