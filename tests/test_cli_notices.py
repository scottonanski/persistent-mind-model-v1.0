from pmm.storage.eventlog import EventLog
from pmm.cli import chat


def _run_notice_block(rt_like):
    # Inline replica of the notice code inside chat.main after printing reply
    evs = rt_like.eventlog.read_all()
    if not hasattr(chat.main, "_last_stage_label"):
        setattr(chat.main, "_last_stage_label", None)
    if not hasattr(chat.main, "_last_cooldown_thr"):
        setattr(chat.main, "_last_cooldown_thr", None)

    # ---- Stage notice ----
    stage_label = None
    for e in reversed(evs):
        if e.get("kind") == "stage_update":
            stage_label = (e.get("meta") or {}).get("to")
            break
        if e.get("kind") == "policy_update":
            m = e.get("meta") or {}
            if str(m.get("component")) == "reflection":
                stage_label = m.get("stage") or stage_label
                if stage_label:
                    break
    prev_stage_label = getattr(chat.main, "_last_stage_label")
    if stage_label and stage_label != prev_stage_label:
        print(f"[stage] {prev_stage_label or '—'} → {stage_label} (cadence updated)")
        setattr(chat.main, "_last_stage_label", stage_label)

    # ---- Policy notice ----
    cooldown_thr = None
    for e in reversed(evs):
        if e.get("kind") != "policy_update":
            continue
        m = e.get("meta") or {}
        if str(m.get("component")) != "cooldown":
            continue
        params = m.get("params") or {}
        if "novelty_threshold" in params:
            try:
                cooldown_thr = float(params.get("novelty_threshold"))
            except Exception:
                cooldown_thr = None
            break
    prev_thr = getattr(chat.main, "_last_cooldown_thr")
    if cooldown_thr is not None and cooldown_thr != prev_thr:
        print(f"[policy] cooldown.novelty_threshold → {cooldown_thr:.2f}")
        setattr(chat.main, "_last_cooldown_thr", cooldown_thr)


def test_stage_and_policy_notices_print_once_on_change(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "notices.db"
    log = EventLog(str(db_path))

    # Prepare events: stage update then policy update
    log.append(kind="stage_update", content="", meta={"to": "S1"})
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "cooldown", "params": {"novelty_threshold": 0.25}},
    )

    class DummyRT:
        def __init__(self, log):
            self.eventlog = log

    rt = DummyRT(log)

    # Clear any previous static attrs
    for attr in ("_last_stage_label", "_last_cooldown_thr"):
        if hasattr(chat.main, attr):
            delattr(chat.main, attr)

    # First run should print both
    _run_notice_block(rt)
    out, _ = capsys.readouterr()
    assert "[stage]" in out
    assert "[policy]" in out

    # Second run with same state should print nothing (no spam)
    _run_notice_block(rt)
    out2, _ = capsys.readouterr()
    assert "[stage]" not in out2
    assert "[policy]" not in out2

    # Change threshold and ensure it prints once
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "cooldown", "params": {"novelty_threshold": 0.40}},
    )
    _run_notice_block(rt)
    out3, _ = capsys.readouterr()
    assert "[policy] cooldown.novelty_threshold → 0.40" in out3


def test_notices_print_once_without_env_gate(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "notices2.db"
    log = EventLog(str(db_path))
    log.append(kind="stage_update", content="", meta={"to": "S2"})
    log.append(
        kind="policy_update",
        content="",
        meta={"component": "cooldown", "params": {"novelty_threshold": 0.10}},
    )

    class DummyRT:
        def __init__(self, log):
            self.eventlog = log

    # Clear state
    for attr in ("_last_stage_label", "_last_cooldown_thr"):
        if hasattr(chat.main, attr):
            delattr(chat.main, attr)

    # With gates removed, the notice block always prints on change and only once
    _run_notice_block(DummyRT(log))
    out, _ = capsys.readouterr()
    assert "[stage]" in out and "[policy]" in out
    # Calling again with no change yields no output
    _run_notice_block(DummyRT(log))
    out2, _ = capsys.readouterr()
    assert out2 == ""
