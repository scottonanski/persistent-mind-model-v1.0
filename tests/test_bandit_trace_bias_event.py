from __future__ import annotations

from pmm.runtime.loop import AutonomyLoop
from pmm.runtime.reflection_bandit import ARMS as BANDIT_ARMS
from pmm.runtime.reflection_bandit import EPS_BIAS
from pmm.storage.eventlog import EventLog


def test_bias_event_emitted_once_and_before_choice_in_reflect_path(tmp_path):
    db = tmp_path / "biastrace.db"
    log = EventLog(str(db))

    print("\n=== Starting test ===")
    print(f"Using database at: {db}")

    class _CDOK:
        def should_reflect(self, **kw):
            print("\n=== _CDOK.should_reflect called ===")
            print(f"kwargs: {kw}")
            return (True, "ok")

        def reset(self):
            print("\n=== _CDOK.reset called ===")
            pass

    print("\n=== Creating AutonomyLoop ===")
    # Initialize the event log with S1 stage
    log.append(
        kind="stage_progress",
        content="",
        meta={"from_stage": "S0", "to_stage": "S1", "reason": "test_init"},
    )

    # Initialize the bandit with some rewards to ensure it has data
    for arm in BANDIT_ARMS:
        log.append(kind="bandit_reward", content="", meta={"arm": arm, "reward": 0.5})

    loop = AutonomyLoop(
        eventlog=log,
        cooldown=_CDOK(),
        interval_seconds=0.01,
        bootstrap_identity=False,  # We already initialized the stage
    )

    # Add a test reflection first to ensure we have a valid reflection
    print("\n=== Adding test reflection ===")
    log.append(
        kind="reflection", content="Test reflection content", meta={"reason": "test"}
    )

    print("\n=== Calling loop.tick() ===")
    loop.tick()

    print("\n=== Reading all events from log ===")
    evs = log.read_all()

    print("\n=== All events in log:")
    for i, e in enumerate(evs):
        print(f"{i}: {e.get('kind')} - {e.get('meta', {}).get('reason', '')}")

    bias = [e for e in evs if e.get("kind") == "bandit_guidance_bias"]
    chosen = [e for e in evs if e.get("kind") == "bandit_arm_chosen"]

    print("\n=== Summary ===")
    print(f"Found {len(bias)} bandit_guidance_bias events")
    print(f"Found {len(chosen)} bandit_arm_chosen events")

    if bias:
        print("\nBandit bias event details:")
        for i, b in enumerate(bias):
            print(f"Bias event {i}:")
            print(f"  ID: {b.get('id')}")
            print(f"  Delta: {b.get('meta', {}).get('delta')}")

    if chosen:
        print("\nBandit arm chosen event details:")
        for i, c in enumerate(chosen):
            print(f"Chosen event {i}:")
            print(f"  ID: {c.get('id')}")
            print(f"  Arm: {c.get('meta', {}).get('arm')}")

    assert len(bias) == 1
    assert len(chosen) == 1
    assert int(bias[0].get("id") or 0) < int(chosen[0].get("id") or 0)

    # meta.delta should include all arms and be bounded
    from pmm.runtime.reflection_bandit import ARMS

    delta = (bias[0].get("meta") or {}).get("delta") or {}
    assert set(delta.keys()) == set(ARMS)
    assert all(abs(float(v)) <= EPS_BIAS for v in delta.values())

    # Unknown/missing type/score should produce zero deltas; simulate by emitting a bias with empty items
    # We don't control the internal builder here, but we can assert the structure holds.
