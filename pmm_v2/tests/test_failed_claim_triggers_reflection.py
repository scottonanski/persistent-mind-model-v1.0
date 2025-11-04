from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


class BadClaimAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "CLAIM:event_existence={\"id\": 424242}"


def test_failed_claim_triggers_reflection():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=BadClaimAdapter())
    events = loop.run_turn("hi")
    kinds = [e["kind"] for e in events if e["kind"] != "autonomy_rule_table"]
    assert kinds[0] == "user_message"
    assert kinds[1] == "assistant_message"
    assert "commitment_open" not in kinds
    assert kinds[-2] == "autonomy_tick"
    assert kinds[-1] == "reflection"
    assert events[-1]["meta"].get("source") == "autonomy_kernel"
