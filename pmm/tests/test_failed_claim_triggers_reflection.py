# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class BadClaimAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return 'CLAIM:event_existence={"id": 424242}'


def test_failed_claim_triggers_reflection():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=BadClaimAdapter(), autonomy=False)
    events = loop.run_turn("hi")
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
            "meta_summary",
            "summary_update",
        )
    ]
    assert kinds[0] == "user_message"
    assert kinds[1] == "assistant_message"
    assert "commitment_open" not in kinds
    assert kinds[-2] == "reflection"
    assert kinds[-1] == "reflection"
    last_reflection = [e for e in events if e["kind"] == "reflection"][-1]
    assert last_reflection["meta"].get("source") is None
