from __future__ import annotations

from pmm_v2.core.event_log import EventLog
from pmm_v2.core.commitment_manager import CommitmentManager
from pmm_v2.runtime.cli import (
    RSM_HELP_TEXT,
    handle_goals_command,
    handle_rsm_command,
)


def _seed_events_for_rsm(log: EventLog) -> int:
    log.append(
        kind="assistant_message",
        content="Determinism anchors the response.",
        meta={},
    )
    baseline_id = log.read_all()[-1]["id"]

    for idx in range(5):
        log.append(
            kind="assistant_message",
            content=f"Determinism perspective {idx}",
            meta={},
        )

    for _ in range(4):
        log.append(
            kind="assistant_message",
            content="CLAIM: failed to explain memory formation.",
            meta={"topic": "memory"},
        )

    return baseline_id


def _line_with_prefix(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if line.strip().startswith(prefix):
            return line.strip()
    return ""


def test_rsm_diff_command_shows_delta():
    log = EventLog(":memory:")
    start_id = _seed_events_for_rsm(log)
    end_id = log.read_all()[-1]["id"]

    output = handle_rsm_command(f"/rsm diff {start_id} {end_id}", log)
    assert output is not None
    lines = output.splitlines()
    assert (
        lines[0] == f"RSM Diff ({start_id} -> {end_id})"
        or lines[0] == f"RSM Diff ({start_id} → {end_id})"
    )
    delta_line = _line_with_prefix(output, "determinism_emphasis")
    assert delta_line
    assert delta_line.endswith("5")
    added_line = _line_with_prefix(output, "Gaps Added")
    assert "memory" in added_line


def test_rsm_invalid_event_id_errors_gracefully():
    log = EventLog(":memory:")
    message = handle_rsm_command("/rsm diff a b", log)
    assert message == "Event ids must be integers."

    message = handle_rsm_command("/rsm -5", log)
    assert message == "Event ids must be non-negative integers."


def test_rsm_help_includes_all_variants():
    assert "[id | diff <a> <b>]" in RSM_HELP_TEXT


def test_cli_goals_shows_mc_cid_and_goal():
    log = EventLog(":memory:")
    manager = CommitmentManager(log)
    cid = manager.open_internal("analyze_knowledge_gaps", reason="gaps=4")

    output = handle_goals_command(log)
    assert cid in output
    assert "analyze_knowledge_gaps" in output
    assert "Internal goals" in output


def test_goals_empty_when_none():
    log = EventLog(":memory:")
    assert handle_goals_command(log) == "No open internal goals. 0 closed."
