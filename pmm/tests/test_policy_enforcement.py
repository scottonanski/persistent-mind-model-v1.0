# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

from __future__ import annotations

import json

from pmm.core.event_log import EventLog
from pmm.runtime.autonomy_kernel import AutonomyKernel
from pmm.runtime.loop import RuntimeLoop
from pmm.adapters.dummy_adapter import DummyAdapter
from pmm.runtime.cli import handle_pm_command


SENSITIVE = {"config", "checkpoint_manifest", "embedding_add", "retrieval_selection"}


def _last_config(eventlog: EventLog, type_name: str):
    for e in reversed(eventlog.read_all()):
        if e.get("kind") != "config":
            continue
        try:
            data = json.loads(e.get("content") or "{}")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("type") == type_name:
            return e, data
    return None


def test_policy_blocks_cli_sensitive_writes():
    log = EventLog(":memory:")
    # Boot kernel to inject policy
    AutonomyKernel(log)

    # Direct EventLog append for a sensitive kind from cli should raise and create a violation
    try:
        log.append(
            kind="config",
            content=json.dumps({"type": "retrieval", "strategy": "fixed", "limit": 5}),
            meta={"source": "cli"},
        )
        raised = False
    except PermissionError:
        raised = True
    assert raised, "Expected policy to block cli writing config"

    violations = [e for e in log.read_all() if e.get("kind") == "violation"]
    assert violations, "Expected a violation event to be appended"
    v = violations[-1]
    assert (v.get("meta") or {}).get("actor") == "cli"
    assert (v.get("meta") or {}).get("attempt_kind") == "config"

    # CLI checkpoint handler must be forbidden by policy
    out = handle_pm_command("/pm checkpoint", log)
    # If no summary exists yet, handler returns a precondition message;
    # once a summary exists, policy forbids CLI checkpoint writes.
    if out != "Forbidden by policy.":
        # Create a summary anchor then try again
        log.append(kind="summary_update", content="{}", meta={})
        out2 = handle_pm_command("/pm checkpoint", log)
        assert out2 == "Forbidden by policy.", out2


def test_autonomy_initializes_policy_and_retrieval_config():
    log = EventLog(":memory:")
    AutonomyKernel(log)

    # Policy exists and is from autonomy_kernel
    policy = _last_config(log, "policy")
    assert policy is not None
    assert (policy[0].get("meta") or {}).get("source") == "autonomy_kernel"

    # Retrieval config exists and is from autonomy_kernel
    retrieval = _last_config(log, "retrieval")
    assert retrieval is not None
    assert (retrieval[0].get("meta") or {}).get("source") == "autonomy_kernel"
    assert retrieval[1].get("strategy") == "vector"


def test_autonomy_embeddings_selection_verification_checkpoint_and_parity():
    log = EventLog(":memory:")
    kernel = AutonomyKernel(log)

    loop = RuntimeLoop(
        eventlog=log, adapter=DummyAdapter(), replay=False, autonomy=False
    )

    # Generate enough events to meet checkpoint threshold and create selections
    for _ in range(60):
        loop.run_turn("policy enforcement turn")
        # Autonomy maintenance each cycle
        kernel.decide_next_action()

    events = log.read_all()
    msgs = [e for e in events if e.get("kind") in ("user_message", "assistant_message")]
    embs = [e for e in events if e.get("kind") == "embedding_add"]
    coverage = len(embs) / max(1, len(msgs))
    assert coverage >= 0.95, f"embedding coverage too low: {coverage:.3f}"

    # Selections recorded
    sels = [e for e in events if e.get("kind") == "retrieval_selection"]
    assert sels, "Expected retrieval_selection events"

    # Verify the new retrieval pipeline is working correctly
    # Check that selections contain valid event IDs and reasonable content
    for sel in sels[-5:]:  # Check last 5 selections
        try:
            data = json.loads(sel.get("content") or "{}")
        except Exception:
            continue
        selected = data.get("selected") or []
        assert selected, "Selection should not be empty"

        # Verify selected events exist and are reasonable
        for eid in selected[:3]:  # Check first few
            event = next((e for e in events if e.get("id") == eid), None)
            assert event, f"Selected event {eid} should exist"
            # Should be retrievable content
            assert event.get("kind") in (
                "user_message",
                "assistant_message",
                "reflection",
                "claim",
                "commitment_open",
                "summary_update",
                "lifetime_memory",
            ), f"Event {eid} has unexpected kind: {event.get('kind')}"

    # Autonomous checkpoint manifest present (ensure via maintenance if needed)
    manifests = [e for e in events if e.get("kind") == "checkpoint_manifest"]
    if not manifests:
        # Encourage a checkpoint pass with a low threshold
        kernel._maybe_append_checkpoint(M=1)
        events = log.read_all()
        manifests = [e for e in events if e.get("kind") == "checkpoint_manifest"]
    assert manifests, "Expected autonomous checkpoint manifest"
    assert (manifests[-1].get("meta") or {}).get("source") == "autonomy_kernel"

    # No CLI writes for sensitive kinds in this in-memory run
    cli_sensitive = [
        e
        for e in events
        if e.get("kind") in SENSITIVE and (e.get("meta") or {}).get("source") == "cli"
    ]
    assert not cli_sensitive, f"CLI sensitive writes found: {cli_sensitive}"

    # Fast rebuild parity
    from pmm.core.mirror import Mirror

    mirror_full = Mirror(log, enable_rsm=True, listen=False)
    snap_full = mirror_full.rsm_snapshot()
    mirror_fast = Mirror(log, enable_rsm=True, listen=False)
    mirror_fast.rebuild_fast()
    snap_fast = mirror_fast.rsm_snapshot()
    assert snap_fast == snap_full, "rebuild_fast parity failed"
