from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import _maybe_emit_meta_reflection


def test_meta_reflection_every_five_and_reward(tmp_path):
    db = tmp_path / "mr.db"
    log = EventLog(str(db))

    # 10 reflections total → expect 2 meta_reflection emissions (idempotent per multiple-of-5)
    for _ in range(10):
        log.append(kind="reflection", content="", meta={})

    # Call helper twice to prove idempotency (no double-fire within same count)
    _maybe_emit_meta_reflection(log, window=5)
    _maybe_emit_meta_reflection(log, window=5)

    events = log.read_all()
    mrs = [e for e in events if e.get("kind") == "meta_reflection"]
    brs = [
        e
        for e in events
        if e.get("kind") == "bandit_reward"
        and (e.get("meta") or {}).get("source") == "meta_reflection"
    ]

    assert len(mrs) == 2, "Should emit floor(10/5) = 2 meta_reflection events"
    assert len(brs) == len(mrs), "One bandit_reward per meta_reflection"

    for mr in mrs:
        m = mr.get("meta") or {}
        assert m.get("window") == 5
        eff = float(m.get("efficacy", -1))
        assert 0.0 <= eff <= 1.0
        opened = max(1, int(m.get("opened", 0)))
        closed = int(m.get("closed", 0))
        assert abs(eff - (closed / opened)) < 1e-6

    for br in brs:
        bm = br.get("meta") or {}
        assert bm.get("component") == "reflection"
        assert bm.get("source") == "meta_reflection"
        assert int(bm.get("window", 0)) == 5
        rew = float(bm.get("reward", -1))
        assert 0.0 <= rew <= 1.0
