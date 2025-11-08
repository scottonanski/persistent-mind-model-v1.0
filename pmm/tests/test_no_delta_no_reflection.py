from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class NoDeltaAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "Plain response with no markers"


def test_no_reflection_when_no_delta():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=NoDeltaAdapter(), autonomy=False)
    events = loop.run_turn("hello")
    kinds = [
        e["kind"]
        for e in events
        if e["kind"]
        not in (
            "autonomy_rule_table",
            "autonomy_stimulus",
            "rsm_update",
            "config",
            "embedding_add",
        )
    ]
    assert kinds[:2] == ["user_message", "assistant_message"]
    # No commitments or claims should be logged
    assert "commitment_open" not in kinds
    assert "commitment_close" not in kinds
    # Reflection is always synthesized for user turns
    assert "reflection" in kinds
