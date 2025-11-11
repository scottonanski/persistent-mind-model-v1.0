# SPDX-License-Identifier: PMM-1.0

from pmm.core.event_log import EventLog
from pmm.runtime.context_utils import (
    render_graph_context,
    render_identity_claims,
    render_internal_goals,
    render_rsm,
)


def test_render_identity_claims_with_name() -> None:
    log = EventLog(":memory:")
    log.append(
        kind="claim",
        content='CLAIM:name_change={"new_name":"Echo"}',
        meta={"claim_type": "name_change", "validated": True},
    )

    result = render_identity_claims(log)

    assert result == "Identity: name: Echo"


def test_render_identity_claims_empty() -> None:
    log = EventLog(":memory:")

    assert render_identity_claims(log) == ""


def test_render_rsm_with_tendencies() -> None:
    snapshot = {
        "behavioral_tendencies": {"determinism_emphasis": 5},
        "knowledge_gaps": [],
        "interaction_meta_patterns": [],
    }

    result = render_rsm(snapshot)

    assert "Tendencies:" in result
    assert "determinism_emphasis (5)" in result


def test_render_internal_goals_lists_open_commitments() -> None:
    log = EventLog(":memory:")
    log.append(
        kind="commitment_open",
        content="",
        meta={
            "cid": "CID-1",
            "goal": "stabilize_loop",
            "origin": "autonomy_kernel",
        },
    )

    result = render_internal_goals(log)

    assert result == "Internal Goals: CID-1 (stabilize_loop)"


def test_render_graph_context_includes_stats_and_threads() -> None:
    log = EventLog(":memory:")
    # Build minimal graph with > 4 nodes to trigger rendering
    for i in range(5):
        log.append(
            kind="commitment_open",
            content="",
            meta={
                "cid": f"CID-{i}",
                "goal": "maintain_graph",
                "origin": "autonomy_kernel",
            },
        )
    log.append(
        kind="commitment_close",
        content="",
        meta={"cid": "CID-0", "origin": "autonomy_kernel"},
    )

    result = render_graph_context(log)

    assert "Graph" in result or "Graph Context" in result
