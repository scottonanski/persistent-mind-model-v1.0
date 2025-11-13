# SPDX-License-Identifier: PMM-1.0

from __future__ import annotations

from pmm.core.enhancements.stability_metrics import StabilityMetrics


def test_stability_high_when_consistent() -> None:
    events = []
    for i in range(5):
        events.append({"kind": "commitment_open", "id": i})
        events.append({"kind": "commitment_close", "id": i + 100})

    summary = StabilityMetrics().compute(events, [])

    assert summary["overall_stability"] == 1.0
    assert summary["commitment_consistency"] == 1.0
    assert summary["reflection_coherence"] == 1.0


def test_stability_lower_when_inconsistent() -> None:
    events = []
    for i in range(5):
        events.append({"kind": "commitment_open", "id": i})
    events.append({"kind": "commitment_close", "id": 99})

    summary = StabilityMetrics().compute(events, [])

    assert summary["commitment_consistency"] < 1.0
    assert summary["overall_stability"] < 1.0


def test_determinism() -> None:
    events = [
        {"kind": "commitment_open", "id": 1},
        {"kind": "commitment_close", "id": 2},
        {"kind": "commitment_open", "id": 3},
    ]
    meta = [
        {
            "patterns": [
                {"commitment_open": 1, "commitment_close": 0, "reflection": 0},
                {"commitment_open": 0, "commitment_close": 1, "reflection": 0},
            ]
        }
    ]

    metrics = StabilityMetrics().compute(events, meta)
    metrics_again = StabilityMetrics().compute(events, meta)

    assert metrics == metrics_again
