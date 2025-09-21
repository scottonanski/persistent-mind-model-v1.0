import re

from pmm.storage.eventlog import EventLog
from pmm.runtime.loop import emit_reflection, AutonomyLoop
from pmm.runtime.bridge import ResponseRenderer


def _last(events, kind):
    for e in reversed(events):
        if e.get("kind") == kind:
            return e
    return None


def test_voicable_reflection_marks_insight_ready(tmp_path):
    log = EventLog(str(tmp_path / "x.db"))
    # Tick once to set baseline tick counter
    loop = AutonomyLoop(eventlog=log, cooldown=None, interval_seconds=0.01)
    # Mark a commit churn after last autonomy tick by appending open
    log.append(kind="autonomy_tick", content="autonomy heartbeat", meta={})
    log.append(kind="commitment_open", content="", meta={"cid": "c1", "text": "t"})

    # Provide a two-line, sufficiently long reflection so acceptance passes
    rid = emit_reflection(
        log,
        "I will keep answers concise in future replies.\nThis should improve clarity and reduce verbosity.",
    )
    # AutonomyLoop.tick will sweep and append insight_ready if voicable and no response yet
    loop.tick()
    evs = log.read_all()
    ir = _last(evs, "insight_ready")
    assert ir is not None
    assert (ir.get("meta") or {}).get("from_event") == rid


def test_one_shot_append_and_no_duplicates(tmp_path):
    log = EventLog(str(tmp_path / "y.db"))
    renderer = ResponseRenderer()

    # Seed: reflection then insight_ready, but no response yet
    rid = emit_reflection(
        log,
        "I'll try a shorter format next time by focusing on essentials.\nI will also avoid redundancy in future turns.",
    )
    log.append(kind="insight_ready", content="", meta={"from_event": rid, "tick": 1})

    # First render should append the insight
    events = log.read_all()
    text1 = renderer.render(
        "Here is my reply.", {"name": None}, stage=None, events=events
    )
    assert re.search(r"_Insight:_ ", text1) is not None

    # After appending a response event, the next render should not add it again
    log.append(kind="response", content=text1, meta={})
    events2 = log.read_all()
    text2 = renderer.render("Second reply.", {"name": None}, stage=None, events=events2)
    assert "_Insight:_" not in text2


def test_paraphrase_is_deterministic_and_bounded(tmp_path):
    log = EventLog(str(tmp_path / "z.db"))
    renderer = ResponseRenderer()

    rid = emit_reflection(
        log,
        "**I will** explore alternatives next time. Extra details here... More lines.\nAnd more.",
    )
    log.append(kind="insight_ready", content="", meta={"from_event": rid, "tick": 1})
    events = log.read_all()
    out = renderer.render("OK", {"name": None}, stage=None, events=events)

    # Should start with plain 'I will explore alternatives next time'
    assert "_Insight:_ I will explore alternatives next time" in out
    # Ensure <= 140 chars after paraphrase
    m = re.search(r"_Insight:_ (.+)$", out, re.M)
    assert m is not None
    assert len(m.group(1)) <= 140
