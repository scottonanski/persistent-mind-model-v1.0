from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


class NoDeltaAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "Plain response with no markers"


def test_no_reflection_when_no_delta():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=NoDeltaAdapter())
    events = loop.run_turn("hello")
    kinds = [e["kind"] for e in events if e["kind"] != "autonomy_rule_table"]
    assert kinds[:2] == ["user_message", "assistant_message"]
    # No commitments or claims should be logged
    assert "commitment_open" not in kinds
    assert "commitment_close" not in kinds
    # Loop reflection followed by autonomous reflection
    assert kinds[-2] == "autonomy_tick"
    assert kinds[-1] == "reflection"
    assert events[-1]["meta"].get("source") == "autonomy_kernel"
