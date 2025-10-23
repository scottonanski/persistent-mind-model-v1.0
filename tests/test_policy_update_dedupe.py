from __future__ import annotations
from pmm.runtime.eventlog_helpers import append_policy_update_once


class FakeEventLog:
    def __init__(self):
        self.events = []

    def read_tail(self, limit: int = 200):
        return self.events[-limit:]

    def append(self, kind: str, content: str, meta: dict | None = None):
        eid = len(self.events) + 1
        self.events.append({"id": eid, "kind": kind, "content": content, "meta": meta or {}})
        return eid


def test_policy_update_dedupes_by_component_params_stage():
    log = FakeEventLog()
    p = {"novelty_threshold": 0.42}
    # first append: happens
    ok1 = append_policy_update_once(
        log,
        component="cooldown",
        params=p,
        stage="S1",
        tick=1,
        window=200,
    )
    # duplicate with same component/params/stage: suppressed
    ok2 = append_policy_update_once(
        log,
        component="cooldown",
        params={"novelty_threshold": 0.42},
        stage="S1",
        tick=2,
        window=200,
    )
    # different params: allowed
    ok3 = append_policy_update_once(
        log,
        component="cooldown",
        params={"novelty_threshold": 0.50},
        stage="S1",
        tick=3,
        window=200,
    )
    # different stage: allowed
    ok4 = append_policy_update_once(
        log,
        component="cooldown",
        params={"novelty_threshold": 0.50},
        stage="S2",
        tick=4,
        window=200,
    )

    kinds = [
        (e["kind"], e["meta"].get("component"), e["meta"].get("stage"), e["meta"].get("tick"))
        for e in log.events
    ]
    assert ok1 is True and ok2 is False and ok3 is True and ok4 is True
    assert len(log.events) == 3
    assert kinds[0][0] == "policy_update"
