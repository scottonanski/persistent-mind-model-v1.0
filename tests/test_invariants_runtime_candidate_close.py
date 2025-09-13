from pmm.runtime.invariants_rt import run_invariants_tick


class _FakeLog:
    def __init__(self, events):
        self._ev = list(events)

    def read_all(self):
        return list(self._ev)

    def verify_chain(self):
        return True


def test_emits_violation_when_close_without_candidate():
    events = [
        {"kind": "commitment_open", "payload": {"commitment_id": "C1"}},
        {"kind": "commitment_close", "payload": {"commitment_id": "C1"}},
    ]
    out = run_invariants_tick(evlog=_FakeLog(events), build_directives=lambda evs: [])
    viols = [
        e
        for e in out
        if e["kind"] == "invariant_violation"
        and (e.get("payload") or {}).get("code") == "CANDIDATE_BEFORE_CLOSE"
    ]
    assert len(viols) == 1
    assert "commitment_id" in viols[0]["payload"]["details"]
