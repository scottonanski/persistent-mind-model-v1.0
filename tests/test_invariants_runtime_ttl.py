from pmm.runtime.invariants_rt import run_invariants_tick


class _FakeLog:
    def __init__(self, events):
        self._ev = list(events)

    def read_all(self):
        return list(self._ev)

    def verify_chain(self):
        return True


def test_emits_violation_when_ttl_expired_and_open():
    # Use expire_at to avoid needing to stub time.time()
    events = [
        {
            "kind": "commitment_open",
            "ts": 100.0,
            "payload": {"commitment_id": "C2", "expire_at": 101.0},
        },
    ]
    out = run_invariants_tick(evlog=_FakeLog(events), build_directives=lambda evs: [])
    viols = [
        e
        for e in out
        if e["kind"] == "invariant_violation"
        and (e.get("payload") or {}).get("code") == "TTL_OPEN_COMMITMENTS"
    ]
    assert len(viols) == 1
