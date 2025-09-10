from pmm.runtime.invariants import check_invariants


def _ev(id, kind, meta=None, content=""):
    return {"id": id, "kind": kind, "content": content, "meta": meta or {}}


def test_policy_update_idempotence_enforced():
    evs = [
        _ev(
            1,
            "policy_update",
            {
                "component": "reflection",
                "stage": "S0",
                "params": {
                    "min_turns": 2,
                    "min_time_s": 20,
                    "force_reflect_if_stuck": True,
                },
            },
        ),
        _ev(
            2,
            "policy_update",
            {
                "component": "reflection",
                "stage": "S0",
                "params": {
                    "min_turns": 2,
                    "min_time_s": 20,
                    "force_reflect_if_stuck": True,
                },
            },
        ),
    ]
    v = check_invariants(evs)
    assert any("duplicate_policy_update" in s for s in v)


def test_policy_update_stage_coherence(monkeypatch):
    # seed stage_update to S1, then a mismatched policy_update claiming S3
    evs = [
        _ev(
            1,
            "stage_update",
            {"from": None, "to": "S1", "snapshot": {}, "reason": "seed"},
        ),
        _ev(
            2,
            "policy_update",
            {
                "component": "reflection",
                "stage": "S3",
                "params": {
                    "min_turns": 3,
                    "min_time_s": 35,
                    "force_reflect_if_stuck": True,
                },
            },
        ),
    ]
    v = check_invariants(evs)
    assert any("policy:stage_mismatch" in s for s in v)


def test_policy_update_component_schema():
    # Missing min_time_s
    evs = [
        _ev(
            1,
            "policy_update",
            {
                "component": "reflection",
                "stage": "S0",
                "params": {"min_turns": 2, "force_reflect_if_stuck": True},
            },
        )
    ]
    v = check_invariants(evs)
    assert any("reflection_schema_invalid" in s for s in v)

    # Missing drift.mult.neuroticism
    evs2 = [
        _ev(
            1,
            "policy_update",
            {
                "component": "drift",
                "stage": "S1",
                "params": {"mult": {"openness": 1.25, "conscientiousness": 1.1}},
            },
        )
    ]
    v2 = check_invariants(evs2)
    assert any("drift_schema_invalid" in s for s in v2)


def test_insight_ready_must_follow_reflection():
    # from_event points to a non-reflection id
    evs = [_ev(1, "insight_ready", {"from_event": 99, "tick": 1})]
    v = check_invariants(evs)
    assert any("insight:without_preceding_reflection" in s for s in v)


def test_insight_ready_consumed_exactly_once():
    # Case A (OK)
    evs_ok = [
        _ev(1, "reflection"),
        _ev(2, "insight_ready", {"from_event": 1, "tick": 1}),
        _ev(3, "response", {}, "with insight"),
    ]
    v_ok = check_invariants(evs_ok)
    assert v_ok == []

    # Case B (none)
    evs_none = [
        _ev(1, "reflection"),
        _ev(2, "insight_ready", {"from_event": 1, "tick": 1}),
    ]
    v_none = check_invariants(evs_none)
    assert any("insight:unconsumed" in s for s in v_none)

    # Case C (double)
    evs_double = [
        _ev(1, "reflection"),
        _ev(2, "insight_ready", {"from_event": 1, "tick": 1}),
        _ev(3, "response"),
        _ev(4, "response"),
    ]
    v_double = check_invariants(evs_double)
    assert any("insight:over_consumed" in s for s in v_double)
