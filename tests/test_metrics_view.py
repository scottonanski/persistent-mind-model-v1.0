from pmm.runtime.metrics_view import MetricsView
from pmm.storage.eventlog import EventLog


def test_snapshot_and_render(tmp_path, capsys):
    log = EventLog(str(tmp_path / "m1.db"))
    mv = MetricsView()
    # Render prints something meaningful without toggles
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


def test_full_self_model_line_appears_when_metrics_on(tmp_path):
    log = EventLog(str(tmp_path / "m4.db"))
    # Seed identity adopt
    log.append(kind="identity_adopt", content="Casey", meta={"name": "Casey"})
    from pmm.runtime.metrics_view import MetricsView

    mv = MetricsView()
    snap = mv.snapshot(log)
    out = MetricsView.render(snap)
    # identity line with traits vector two decimals
    import re

    assert re.search(
        r"identity=Casey \| stage=S\d \| traits=\[O:\d+\.\d{2} C:\d+\.\d{2} E:\d+\.\d{2} A:\d+\.\d{2} N:\d+\.\d{2}\]",
        out,
    )
    # second line begins with reflect[...] and includes drift_mult
    assert "reflect[minT=" in out and "drift_mult={" in out


def test_stage_policy_values_match_tables(tmp_path, monkeypatch):
    log = EventLog(str(tmp_path / "m5.db"))
    mv = MetricsView()
    mv.on()

    from pmm.runtime.stage_tracker import StageTracker

    # S1
    monkeypatch.setattr(
        StageTracker, "infer_stage", staticmethod(lambda evs: ("S1", {}))
    )
    out1 = MetricsView.render(mv.snapshot(log))
    assert "reflect[minT=3, minS=35]" in out1
    assert (
        "drift_mult={O:1.25, C:1.1, N:1}" in out1
        or "drift_mult={O:1.25, C:1.1, N:1.0}" in out1
    )

    # S3
    monkeypatch.setattr(
        StageTracker, "infer_stage", staticmethod(lambda evs: ("S3", {}))
    )
    out3 = MetricsView.render(mv.snapshot(log))
    assert "reflect[minT=5, minS=70]" in out3
    assert (
        "drift_mult={O:1, C:1.2, N:0.8}" in out3
        or "drift_mult={O:1.0, C:1.2, N:0.8}" in out3
    )


def test_traits_render_two_decimals_and_defaults(tmp_path):
    log = EventLog(str(tmp_path / "m6.db"))
    # Seed identity with partial traits via direct trait_update for O only
    log.append(kind="identity_adopt", content="Ava", meta={"name": "Ava"})
    log.append(
        kind="trait_update", content="", meta={"trait": "openness", "delta": 0.13}
    )

    from pmm.runtime.metrics_view import MetricsView

    mv = MetricsView()
    snap = mv.snapshot(log)
    out = MetricsView.render(snap)
    # Ensure two-decimal formatting and defaults for missing traits
    import re

    m = re.search(
        r"traits=\[O:(\d+\.\d{2}) C:(\d+\.\d{2}) E:(\d+\.\d{2}) A:(\d+\.\d{2}) N:(\d+\.\d{2})\]",
        out,
    )
    assert m is not None
    # All have exactly two decimals
    for i in range(1, 6):
        assert re.match(r"^\d+\.\d{2}$", m.group(i))
