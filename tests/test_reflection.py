from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.loop import evaluate_reflection


def test_cooldown_blocks_until_turns_and_time_pass(tmp_path):
    cd = ReflectionCooldown(min_turns=2, min_seconds=5.0)
    # Initially no turns, last_ts=0; should block due to min_turns first
    ok, reason = evaluate_reflection(cd, now=0.0, novelty=1.0)
    assert (ok, reason) == (False, "min_turns")

    # Note one user turn; still below min_turns
    cd.note_user_turn()
    ok, reason = evaluate_reflection(cd, now=10.0, novelty=1.0)
    assert (ok, reason) == (False, "min_turns")

    # Note second turn
    cd.note_user_turn()
    # To test time blocking, we reset (which also clears turns), then add turns again and check with insufficient time
    cd.reset()
    cd.note_user_turn()
    cd.note_user_turn()
    ok, reason = evaluate_reflection(cd, now=cd.last_ts + 1.0, novelty=1.0)
    assert (ok, reason) == (False, "min_time")


def test_cooldown_allows_when_gates_pass(tmp_path):
    cd = ReflectionCooldown(min_turns=2, min_seconds=5.0)
    # Establish baseline time and turns
    cd.reset()
    cd.note_user_turn()
    cd.note_user_turn()
    ok, reason = evaluate_reflection(cd, now=cd.last_ts + 6.0, novelty=1.0)
    assert (ok, reason) == (True, "ok")


def test_cooldown_blocks_low_novelty(tmp_path):
    cd = ReflectionCooldown(min_turns=2, min_seconds=5.0)
    cd.reset()
    cd.note_user_turn()
    cd.note_user_turn()
    ok, reason = evaluate_reflection(cd, now=cd.last_ts + 6.0, novelty=0.1)
    assert (ok, reason) == (False, "low_novelty")
