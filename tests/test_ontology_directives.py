# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.prompts import SYSTEM_PRIMER, compose_system_prompt


def test_primer_ontology_extensions():
    assert "Self-locate" in SYSTEM_PRIMER
    assert (
        "Continuity: treat each ontological meditation as cumulative" in SYSTEM_PRIMER
    )
    assert "Evolution: when a meditation appears" in SYSTEM_PRIMER
    assert "Concept seeding: emit 1-3 short concept tokens" in SYSTEM_PRIMER
    assert "Reflection vocabulary" in SYSTEM_PRIMER


def test_compose_system_prompt_ontology_directive():
    # history_len triggers meditation condition (74 > 20 and divisible by 37)
    prompt = compose_system_prompt(
        history=[{}],
        open_commitments=[],
        context_has_graph=False,
        history_len=74,
    )
    assert "Emit 1-3 ontological concept tokens" in prompt
    assert "future reasoning" in prompt


def test_meditation_fallback_binds_concepts():
    log = EventLog(":memory:")
    # Seed some events; we'll force the meditation trigger via count override.
    for i in range(5):
        log.append(kind="user_message", content=f"pre{i}", meta={})

    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
    # Force meditation_active path deterministically for the test
    loop.eventlog.count = lambda: 37  # type: ignore[attr-defined]
    loop.run_turn("trigger meditation fallback")

    tokens = set()
    for ev in log.read_all():
        if ev.get("kind") != "concept_bind_event":
            continue
        try:
            data = json.loads(ev.get("content") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("tokens"), list):
            tokens.update(data["tokens"])

    assert {"ontology.structure", "identity.evolution", "awareness.loop"} <= tokens
