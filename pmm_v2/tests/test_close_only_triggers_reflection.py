from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


class CloseAdapter:
    def __init__(self, cid: str) -> None:
        self.cid = cid

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return f"Done\nCLOSE: {self.cid}"


def test_close_only_triggers_reflection():
    log = EventLog(":memory:")
    # Pre-open a commitment
    log.append(kind="commitment_open", content="c", meta={"cid": "abcd", "text": "x"})
    loop = RuntimeLoop(eventlog=log, adapter=CloseAdapter("abcd"))
    events = loop.run_turn("close it")
    kinds = [e["kind"] for e in events if e["kind"] != "autonomy_rule_table"]
    assert kinds[-4:] == ["commitment_close", "reflection", "autonomy_tick", "reflection"]
    assert events[-1]["meta"].get("source") == "autonomy_kernel"
