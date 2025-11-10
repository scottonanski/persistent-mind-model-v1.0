# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/tests/test_exec_binding_idle_monitor.py
from __future__ import annotations

from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop


class IdleMonitorAdapter:
    deterministic_latency_ms = 0

    def generate_reply(
        self, system_prompt: str, user_prompt: str
    ) -> str:  # pragma: no cover
        return "COMMIT: start idle monitor routine"


def test_idle_monitor_binding_escalates_to_internal_goal() -> None:
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=IdleMonitorAdapter(), autonomy=False)

    loop.run_turn("trigger idle monitor")

    router = loop.exec_router
    assert router is not None, "ExecBindRouter should be initialised in runtime mode"

    for _ in range(3):
        router.tick()

    events = log.read_all()
    kinds = {event["kind"] for event in events}

    assert "metric_check" in kinds
    assert "autonomy_kernel" in kinds
    assert "internal_goal_created" in kinds
    assert any(
        event["kind"] == "commitment_open"
        and (event.get("meta") or {}).get("goal") == "explore_rsm_drift"
        and (event.get("meta") or {}).get("origin") == "autonomy_kernel"
        for event in events
    )
