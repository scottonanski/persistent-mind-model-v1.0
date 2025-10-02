from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, AutonomyLoop


def _mk_rt(tmp_path):
    db = tmp_path / "ttl_ticks.db"
    log = EventLog(str(db))
    rt = Runtime(
        LLMConfig(
            provider="openai", model="gpt-4o", embed_provider=None, embed_model=None
        ),
        log,
    )
    return rt, log


def _run_ticks(log: EventLog, rt: Runtime, n: int):
    loop = AutonomyLoop(eventlog=log, cooldown=rt.cooldown, interval_seconds=0.001)
    for _ in range(n):
        loop.tick()


def test_expire_after_ttl(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Open a commitment structurally
    from pmm.commitments.tracker import CommitmentTracker

    CommitmentTracker(log).add_commitment("write the report", source="test")

    # Get the CID of the test commitment before ticks
    model_before = build_self_model(log.read_all())
    test_cid = list(model_before["commitments"]["open"].keys())[0]

    # Advance > TTL (default 10 ticks)
    _run_ticks(log, rt, 11)

    evs = log.read_all()
    kinds = [e.get("kind") for e in evs]
    assert "commitment_expire" in kinds

    # Check that our specific test commitment expired
    model = build_self_model(evs)
    assert test_cid not in model.get("commitments", {}).get("open", {})
    assert test_cid in model.get("commitments", {}).get("expired", {})


def test_no_expire_if_recent_activity(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Open a commitment structurally
    from pmm.commitments.tracker import CommitmentTracker

    CommitmentTracker(log).add_commitment("draft the design doc", source="test")
    # Fewer than TTL ticks
    _run_ticks(log, rt, 5)

    evs = log.read_all()
    kinds = [e.get("kind") for e in evs]
    assert "commitment_expire" not in kinds
    model = build_self_model(evs)
    assert len(model.get("commitments", {}).get("open", {})) >= 1


def test_snooze_delays_expire(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Open structurally
    from pmm.commitments.tracker import CommitmentTracker

    CommitmentTracker(log).add_commitment("update the docs", source="test")

    # Get the CID of the test commitment
    model_before = build_self_model(log.read_all())
    test_cid = list(model_before["commitments"]["open"].keys())[0]

    # Add snooze until tick 15
    log.append(
        kind="commitment_snooze",
        content="",
        meta={
            "cid": test_cid,
            "until_tick": 15,
        },
    )
    _run_ticks(log, rt, 12)  # now tick ~12

    # Check that our specific commitment did NOT expire (snoozed until tick 15)
    model_after = build_self_model(log.read_all())
    assert test_cid in model_after.get("commitments", {}).get(
        "open", {}
    ), "Snoozed commitment should still be open at tick 12 (snoozed until tick 15)"


def test_no_premature_expire_if_evidence_within_ttl(tmp_path, monkeypatch):
    rt, log = _mk_rt(tmp_path)
    # Open a commitment structurally
    from pmm.commitments.tracker import CommitmentTracker

    CommitmentTracker(log).add_commitment("finish the report", source="test")

    # Later reply provides evidence of completion
    # Free-text evidence is ignored by runtime; structural close requires explicit call
    # (This test asserts only that no premature expire occurs within TTL.)

    # Run ticks fewer than TTL (default 10)
    _run_ticks(log, rt, 5)

    evs = log.read_all()
    kinds = [e["kind"] for e in evs]

    # With artifact-required policy, evidence without artifact does not close; ensure no premature expire
    assert "commitment_expire" not in kinds
