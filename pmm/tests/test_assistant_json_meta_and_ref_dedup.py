# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


def test_assistant_json_meta_is_captured(tmp_path):
    db = str(tmp_path / "json_meta.db")
    log = EventLog(db)

    class JsonAdapter:
        deterministic_latency_ms = 0
        model = "test-json-adapter"

        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            return json.dumps(
                {
                    "intent": "plan",
                    "outcome": "noted",
                    "next": "monitor",
                    "self_model": "ok",
                }
            )

    loop = RuntimeLoop(eventlog=log, adapter=JsonAdapter(), autonomy=False)
    loop.run_turn("hello")

    events = log.read_all()
    ai = [e for e in events if e.get("kind") == "assistant_message"][-1]
    meta = ai.get("meta") or {}
    # Optional structured payload is attached without changing content
    assert meta.get("assistant_structured") is True
    assert meta.get("assistant_schema") == "assistant.v1"
    payload = meta.get("assistant_payload")
    assert isinstance(payload, str) and payload.startswith("{")
    parsed = json.loads(payload)
    assert set(parsed.keys()) == {"intent", "outcome", "next", "self_model"}


def test_inter_ledger_ref_is_deduplicated(tmp_path):
    db = str(tmp_path / "ref_dedup.db")
    log = EventLog(db)

    class Adapter:
        deterministic_latency_ms = 0
        model = "test-ref-adapter"

        def __init__(self):
            self.mode = 0

        def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
            if self.mode == 0:
                return "ok"
            # Open one commitment so autonomy reflect considers refs
            return "Working\nCOMMIT: c1"

    adapter = Adapter()
    loop = RuntimeLoop(
        eventlog=log,
        adapter=adapter,
        autonomy=False,
        thresholds={
            "reflection_interval": 1,
            "summary_interval": 9999,
            "commitment_staleness": 5,
            "commitment_auto_close": 10,
        },
    )

    # First turn: no-op
    loop.run_turn("hello")
    # Second turn: open a commitment
    adapter.mode = 1
    loop.run_turn("open")

    # Trigger two reflections; the kernel should not emit duplicate REF targets
    loop.run_tick(slot=0, slot_id="S1")
    loop.run_tick(slot=0, slot_id="S2")

    inter_refs = [e for e in log.read_all() if e.get("kind") == "inter_ledger_ref"]
    # Should only be a single inter_ledger_ref for the same target
    assert len(inter_refs) == 1
