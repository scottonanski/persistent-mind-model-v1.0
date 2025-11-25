# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.prompts import (
    SYSTEM_PRIMER,
    compose_system_prompt,
    _MEDITATION_CONCEPT_HINTS,
)


def test_primer_ontology_extensions():
    assert "Self-locate" in SYSTEM_PRIMER
    assert (
        "Continuity: treat each ontological meditation as cumulative" in SYSTEM_PRIMER
    )
    assert "Evolution: when a meditation appears" in SYSTEM_PRIMER
    assert "Concept seeding: emit 1-3 short concept tokens" in SYSTEM_PRIMER
    assert "Reflection vocabulary" in SYSTEM_PRIMER
    # New: Identity continuity directive (B enhancement)
    assert "Identity continuity: your narrative identity persists" in SYSTEM_PRIMER


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
    # New: Meditation scaffold with continuity context (E enhancement)
    assert "evolving identity" in prompt
    assert "prior ontological meditations" in prompt


def test_meditation_concept_focus_hints():
    """Test that meditation injection includes concept focus hints (E enhancement)."""
    prompt = compose_system_prompt(
        history=[{}],
        open_commitments=[],
        context_has_graph=False,
        history_len=74,  # Triggers meditation index 2 (74 // 37 = 2)
    )
    # Meditation index 2 should have hint "identity.naming"
    assert "concept focus: identity.naming" in prompt


def test_meditation_concept_hints_mapping():
    """Test that all 11 meditations have concept hints defined."""
    assert len(_MEDITATION_CONCEPT_HINTS) == 11
    for i in range(11):
        assert i in _MEDITATION_CONCEPT_HINTS
        assert isinstance(_MEDITATION_CONCEPT_HINTS[i], str)
        assert "." in _MEDITATION_CONCEPT_HINTS[i]  # Format: category.subcategory


def test_self_model_guidance_in_prompt():
    """Test that self_model field guidance is included (D enhancement)."""
    prompt = compose_system_prompt(
        history=[{}],
        open_commitments=[],
        context_has_graph=False,
    )
    assert 'In the "self_model" field' in prompt
    assert "vocabulary consistency" in prompt
    assert "ledger-verifiable facts" in prompt


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


def test_universal_continuity_fallback():
    """Test that every turn gets at least identity.continuity concept (C enhancement)."""
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=DummyAdapter(), autonomy=False)
    # Normal turn without meditation trigger - should still get continuity concept
    loop.run_turn("hello world")

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

    assert "identity.continuity" in tokens
