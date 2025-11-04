from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.runtime.loop import RuntimeLoop


class CloseAdapter:
    def __init__(self, cid: str) -> None:
        self.cid = cid

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return f"CLOSE: {self.cid}"


def test_idempotent_closure():
    log = EventLog(":memory:")
    # pre-open
    log.append(kind="commitment_open", content="c", meta={"cid": "abcd", "text": "x"})
    loop = RuntimeLoop(eventlog=log, adapter=CloseAdapter("abcd"), autonomy=False)
    # First turn closes and reflects
    events1 = loop.run_turn("do close")
    kinds1 = [e["kind"] for e in events1 if e["kind"] not in ("autonomy_rule_table", "autonomy_stimulus")]
    assert kinds1.count("commitment_close") == 1
    assert kinds1[-3:] == ["reflection", "commitment_close", "reflection"]
    last_reflection1 = [e for e in events1 if e["kind"] == "reflection"][-1]
    assert last_reflection1["meta"].get("source") is None

    # Second turn attempts to close again; should not close
    events2 = loop.run_turn("do close again")
    kinds2 = [e["kind"] for e in events2 if e["kind"] not in ("autonomy_rule_table", "autonomy_stimulus")]
    assert kinds2.count("commitment_close") == 1
    assert kinds2[-1] == "summary_update"
