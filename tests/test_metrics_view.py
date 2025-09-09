from pmm.runtime.metrics_view import MetricsView
from pmm.storage.eventlog import EventLog


def test_toggle_on_off_and_render(tmp_path, capsys):
    log = EventLog(str(tmp_path / "m1.db"))
    mv = MetricsView()
    assert mv.enabled is False
    mv.on()
    assert mv.enabled is True
    mv.off()
    assert mv.enabled is False

    # When enabled, render prints something meaningful
    mv.on()
    snap = mv.snapshot(log)
    out = MetricsView.render(snap)
    assert "[METRICS]" in out


def test_snapshot_composition(tmp_path):
    log = EventLog(str(tmp_path / "m2.db"))
    # Seed events: autonomy_tick, debug skip, stage_update, priority_update, and opens
    log.append(
        kind="autonomy_tick", content="", meta={"telemetry": {"IAS": 0.62, "GAS": 0.44}}
    )
    log.append(kind="debug", content="", meta={"reflect_skip": "novelty_low"})
    log.append(
        kind="stage_update",
        content="",
        meta={"from": None, "to": "S1", "snapshot": {}, "reason": "seed"},
    )
    log.append(
        kind="priority_update",
        content="",
        meta={"ranking": [{"cid": "a1", "score": 0.81}, {"cid": "b2", "score": 0.63}]},
    )
    log.append(kind="commitment_open", content="", meta={"cid": "a1", "text": "alpha"})
    log.append(kind="commitment_open", content="", meta={"cid": "b2", "text": "bravo"})

    mv = MetricsView()
    snap = mv.snapshot(log)
    assert snap["telemetry"]["IAS"] == 0.62
    assert snap["telemetry"]["GAS"] == 0.44
    assert snap["reflect_skip"] == "novelty_low"
    assert snap["stage"] == "S1"
    assert snap["open_commitments"]["count"] == 2
    assert len(snap["open_commitments"]["top3"]) == 2
    assert snap["priority_top5"][0]["cid"] == "a1"


def test_no_side_effects(tmp_path):
    log = EventLog(str(tmp_path / "m3.db"))
    mv = MetricsView()
    before = len(log.read_all())
    _ = mv.snapshot(log)
    after = len(log.read_all())
    assert before == after, "snapshot must not append any events"
