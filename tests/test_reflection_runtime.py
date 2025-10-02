from pmm.config import REFLECTION_REJECTED, REFLECTION_SKIPPED
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import maybe_reflect
from pmm.storage.eventlog import EventLog


def test_no_reflect_emits_skip_breadcrumb(tmp_path):
    db = tmp_path / "rt1.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=2, min_seconds=60.0)

    # Establish recent baseline time
    cd.reset()
    # Two quick turns, but not enough time
    # Use novelty < 0.95 to avoid high-novelty bypass
    cd.note_user_turn()
    cd.note_user_turn()
    did, reason = maybe_reflect(log, cd, now=cd.last_ts + 1.0, novelty=0.8)
    assert did is False
    assert reason == "min_time"

    evs = log.read_all()
    skips = [e for e in evs if e["kind"] == REFLECTION_SKIPPED]
    assert skips and (skips[-1].get("meta") or {}).get("reason") == "min_time"


def test_reflect_resets_cooldown(tmp_path):
    db = tmp_path / "rt2.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=2, min_seconds=1.0)

    cd.reset()
    cd.note_user_turn()
    cd.note_user_turn()

    # Enough time elapsed to pass time gate
    did, reason = maybe_reflect(
        log,
        cd,
        now=cd.last_ts + 2.0,
        novelty=1.0,
        llm_generate=lambda context: (
            "This is a test reflection with sufficient content.\n"
            "It has multiple lines to pass the requirements."
        ),
    )
    assert did is True and reason == "ok"

    # Cooldown should reset turns
    assert cd.turns_since == 0

    events = log.read_all()
    kinds = [e["kind"] for e in events]
    # A reflection may be rejected by the acceptance gate; accept either outcome
    if "reflection" in kinds:
        refl = [e for e in events if e["kind"] == "reflection"]
        meta = refl[-1].get("meta") or {}
        tel = meta.get("telemetry") or {}
        assert 0.0 <= tel.get("IAS", 0.0) <= 1.0
        assert 0.0 <= tel.get("GAS", 0.0) <= 1.0
    else:
        # If rejected, a reflection_rejected breadcrumb is emitted
        rejects = [
            e
            for e in events
            if e.get("kind") == REFLECTION_REJECTED
            and (e.get("meta") or {}).get("reason")
        ]
        assert (
            rejects
        ), "expected a reflection_rejected breadcrumb when no reflection is emitted"


def test_policy_shadow_invokes_graph(tmp_path):
    class StubGraph:
        def __init__(self):
            self.calls = []

        def policy_updates_for_reflection(self, rid: int):
            self.calls.append(rid)
            return []

    db = tmp_path / "policy_shadow.db"
    log = EventLog(str(db))
    cd = ReflectionCooldown(min_turns=0, min_seconds=0.0)
    cd.reset()

    graph = StubGraph()

    did, reason = maybe_reflect(
        log,
        cd,
        now=0.0,
        novelty=1.0,
        llm_generate=lambda context: (
            "Reflection with enough substance to record.\n" "Line 2 ensures length."
        ),
        memegraph=graph,
    )
    assert did is True and reason == "ok"
    assert graph.calls, "expected MemeGraph shadow to be invoked"
