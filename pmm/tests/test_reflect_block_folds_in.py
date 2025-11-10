# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class ReflectOnlyAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        block = {"observations": ["o1"], "next": ["n1"], "corrections": ["c1"]}
        return "REFLECT:" + json.dumps(block)


def test_reflect_block_triggers_reflection_and_folds_content():
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=ReflectOnlyAdapter(), autonomy=False)
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
        )
    ]
    assert kinds[0] == "user_message"
    assert "assistant_message" in kinds
    assert kinds.count("reflection") == 2
    assert kinds[-1] == "reflection"
    auto_refl = [e for e in events if e["kind"] == "reflection"][-1]
    manual_refl = [
        e
        for e in events
        if e["kind"] == "reflection"
        and e.get("meta", {}).get("source") != "autonomy_kernel"
    ][-1]
    manual_text = manual_refl["content"]
    assert "Observations: o1." in manual_text
    assert "Corrections: c1." in manual_text
    assert "Next: n1." in manual_text
    assert auto_refl["meta"].get("source") is None
