"""Integration tests for context-aware bandit learning.

Verifies that the bandit learns stage-specific arm preferences and uses
stage context during exploitation.
"""


from pmm.runtime.loop import io as _io
from pmm.runtime.reflection_bandit import _arm_rewards, choose_arm
from pmm.storage.eventlog import EventLog


def test_stage_filtered_reward_aggregation(tmp_path):
    """Verify rewards are correctly filtered by stage context."""
    db = tmp_path / "test.db"
    evlog = EventLog(str(db))

    # Create rewards for different stages
    # S0: succinct performs well (0.8)
    _io.append_bandit_reward(
        evlog, component="reflection", arm="succinct", reward=0.8, extra={"stage": "S0"}
    )
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="succinct",
        reward=0.85,
        extra={"stage": "S0"},
    )

    # S0: narrative performs poorly (0.3)
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="narrative",
        reward=0.3,
        extra={"stage": "S0"},
    )

    # S1: question_form performs well (0.9)
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="question_form",
        reward=0.9,
        extra={"stage": "S1"},
    )
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="question_form",
        reward=0.85,
        extra={"stage": "S1"},
    )

    # S1: succinct performs poorly (0.4)
    _io.append_bandit_reward(
        evlog, component="reflection", arm="succinct", reward=0.4, extra={"stage": "S1"}
    )

    events = evlog.read_all()

    # Test global aggregation (no stage filter)
    global_rewards = _arm_rewards(events, stage=None)
    assert len(global_rewards["succinct"]) == 3  # 2 from S0 + 1 from S1
    assert len(global_rewards["narrative"]) == 1
    assert len(global_rewards["question_form"]) == 2

    # Test S0-filtered aggregation
    s0_rewards = _arm_rewards(events, stage="S0")
    assert len(s0_rewards["succinct"]) == 2  # Only S0 rewards
    assert len(s0_rewards["narrative"]) == 1
    assert len(s0_rewards["question_form"]) == 0  # No S0 question_form rewards

    # Verify S0 means
    s0_succinct_mean = sum(s0_rewards["succinct"]) / len(s0_rewards["succinct"])
    s0_narrative_mean = sum(s0_rewards["narrative"]) / len(s0_rewards["narrative"])
    assert s0_succinct_mean > 0.8  # Good performance
    assert s0_narrative_mean < 0.4  # Poor performance

    # Test S1-filtered aggregation
    s1_rewards = _arm_rewards(events, stage="S1")
    assert len(s1_rewards["question_form"]) == 2  # Only S1 rewards
    assert len(s1_rewards["succinct"]) == 1
    assert len(s1_rewards["narrative"]) == 0

    # Verify S1 means
    s1_question_mean = sum(s1_rewards["question_form"]) / len(
        s1_rewards["question_form"]
    )
    s1_succinct_mean = sum(s1_rewards["succinct"]) / len(s1_rewards["succinct"])
    assert s1_question_mean > 0.85  # Good performance
    assert s1_succinct_mean < 0.5  # Poor performance


def test_context_aware_arm_selection_exploitation(tmp_path):
    """Verify choose_arm uses stage-specific history during exploitation."""
    db = tmp_path / "test.db"
    evlog = EventLog(str(db))

    # Seed many rewards to reduce exploration (epsilon=0.1)
    # S0: succinct is best (0.9 mean)
    for _ in range(10):
        _io.append_bandit_reward(
            evlog,
            component="reflection",
            arm="succinct",
            reward=0.9,
            extra={"stage": "S0"},
        )

    # S0: narrative is worst (0.2 mean)
    for _ in range(10):
        _io.append_bandit_reward(
            evlog,
            component="reflection",
            arm="narrative",
            reward=0.2,
            extra={"stage": "S0"},
        )

    # S1: question_form is best (0.95 mean)
    for _ in range(10):
        _io.append_bandit_reward(
            evlog,
            component="reflection",
            arm="question_form",
            reward=0.95,
            extra={"stage": "S1"},
        )

    # S1: succinct is mediocre (0.5 mean)
    for _ in range(10):
        _io.append_bandit_reward(
            evlog,
            component="reflection",
            arm="succinct",
            reward=0.5,
            extra={"stage": "S1"},
        )

    # Add autonomy ticks for choose_arm
    for i in range(5):
        evlog.append("autonomy_tick", "", {"tick": i + 1})

    events = evlog.read_all()

    # Test S0 context: should prefer succinct (0.9) over narrative (0.2)
    # Run multiple times to account for epsilon-greedy exploration
    s0_choices = []
    for _ in range(20):
        arm, _ = choose_arm(events, stage="S0")
        s0_choices.append(arm)

    # With epsilon=0.1, expect ~90% succinct, ~10% exploration
    succinct_ratio = s0_choices.count("succinct") / len(s0_choices)
    assert succinct_ratio > 0.7, f"Expected mostly succinct in S0, got {s0_choices}"

    # Test S1 context: should prefer question_form (0.95) over succinct (0.5)
    s1_choices = []
    for _ in range(20):
        arm, _ = choose_arm(events, stage="S1")
        s1_choices.append(arm)

    question_ratio = s1_choices.count("question_form") / len(s1_choices)
    assert (
        question_ratio > 0.7
    ), f"Expected mostly question_form in S1, got {s1_choices}"


def test_legacy_label_normalization_in_context(tmp_path):
    """Verify legacy 'question' labels normalize to 'question_form' in context filtering."""
    db = tmp_path / "test.db"
    evlog = EventLog(str(db))

    # Create rewards with legacy "question" label
    _io.append_bandit_reward(
        evlog, component="reflection", arm="question", reward=0.8, extra={"stage": "S1"}
    )
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="question",
        reward=0.85,
        extra={"stage": "S1"},
    )

    # Create rewards with new "question_form" label
    _io.append_bandit_reward(
        evlog,
        component="reflection",
        arm="question_form",
        reward=0.9,
        extra={"stage": "S1"},
    )

    events = evlog.read_all()

    # Both should aggregate under "question_form"
    s1_rewards = _arm_rewards(events, stage="S1")
    assert len(s1_rewards["question_form"]) == 3  # 2 legacy + 1 new
    assert s1_rewards["question_form"] == [0.8, 0.85, 0.9]


def test_rewards_without_stage_metadata_aggregate_globally(tmp_path):
    """Verify rewards without stage metadata are included in global aggregation only."""
    db = tmp_path / "test.db"
    evlog = EventLog(str(db))

    # Rewards with stage
    _io.append_bandit_reward(
        evlog, component="reflection", arm="succinct", reward=0.8, extra={"stage": "S0"}
    )

    # Rewards without stage (legacy or fallback)
    evlog.append(
        "bandit_reward",
        "",
        {"component": "reflection", "arm": "succinct", "reward": 0.7},
    )

    events = evlog.read_all()

    # Global aggregation includes both
    global_rewards = _arm_rewards(events, stage=None)
    assert len(global_rewards["succinct"]) == 2

    # Stage-filtered aggregation excludes legacy
    s0_rewards = _arm_rewards(events, stage="S0")
    assert len(s0_rewards["succinct"]) == 1  # Only the one with stage="S0"


def test_context_aware_selection_with_no_stage_history(tmp_path):
    """Verify graceful handling when stage has no reward history (cold start)."""
    db = tmp_path / "test.db"
    evlog = EventLog(str(db))

    # Only S0 rewards exist
    _io.append_bandit_reward(
        evlog, component="reflection", arm="succinct", reward=0.8, extra={"stage": "S0"}
    )

    evlog.append("autonomy_tick", "", {"tick": 1})
    events = evlog.read_all()

    # Request S1 context (no history)
    # Should still return a valid arm (exploration or fallback)
    arm, _ = choose_arm(events, stage="S1")
    assert arm in ["succinct", "question_form", "narrative", "checklist", "analytical"]
