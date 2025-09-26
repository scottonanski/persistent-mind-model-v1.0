import logging

import pytest
from pmm.runtime.stage_manager import StageManager
from pmm.storage.eventlog import EventLog
from pmm.constants import EventKinds
from pmm.runtime.memegraph import MemeGraphProjection
from helpers.stage_seeding import (
    _seed_reflections,
    _seed_restructures,
    _seed_metrics,
)


@pytest.fixture
def eventlog(tmp_path):
    return EventLog(str(tmp_path / "test_stage.db"))


def _collect_inputs(log: EventLog):
    evs = log.read_all()
    refs = [e for e in evs if e.get("kind") == EventKinds.REFLECTION]
    evols = [e for e in evs if e.get("kind") == EventKinds.EVOLUTION]
    intros = [e for e in evs if e.get("kind") == EventKinds.INTROSPECTION_QUERY]
    adopts = [e for e in evs if e.get("kind") == EventKinds.IDENTITY_ADOPTION]
    mets = [e for e in evs if e.get("kind") == EventKinds.METRICS_UPDATE]
    if mets:
        ias = float((mets[-1].get("meta") or {}).get("IAS") or 0.0)
        gas = float((mets[-1].get("meta") or {}).get("GAS") or 0.0)
    else:
        ias = gas = 0.0
    return refs, evols, intros, adopts, ias, gas


def test_current_stage_defaults_to_s0(eventlog):
    sm = StageManager(eventlog)
    assert sm.current_stage() == "S0"


def test_s0_criteria_met(eventlog):
    _seed_reflections(eventlog, 3)
    _seed_restructures(eventlog, 2)
    _seed_metrics(eventlog, 0.64, 0.24)
    sm = StageManager(eventlog)
    refs, evols, intros, adopts, ias, gas = _collect_inputs(eventlog)
    assert sm._criteria_met("S0", refs, evols, intros, adopts, ias, gas) is True


def test_s1_criteria_met(eventlog):
    # Seed cumulative events, then verify S1 criteria
    _seed_reflections(eventlog, 5)
    _seed_restructures(eventlog, 4)
    _seed_metrics(eventlog, 0.74, 0.39)
    sm = StageManager(eventlog)
    refs, evols, intros, adopts, ias, gas = _collect_inputs(eventlog)
    assert sm._criteria_met("S1", refs, evols, intros, adopts, ias, gas) is True


def test_no_advance_if_criteria_not_met(eventlog):
    _seed_reflections(eventlog, 1)
    _seed_restructures(eventlog, 0)
    _seed_metrics(eventlog, 0.40, 0.10)
    sm = StageManager(eventlog)
    refs, evols, intros, adopts, ias, gas = _collect_inputs(eventlog)
    assert sm._criteria_met("S0", refs, evols, intros, adopts, ias, gas) is False


def test_hysteresis_buffer_prevents_thrash(eventlog):
    _seed_reflections(eventlog, 2)
    _seed_restructures(eventlog, 1)
    _seed_metrics(eventlog, 0.51, 0.16)  # within hysteresis band for S0
    sm = StageManager(eventlog)
    refs, evols, intros, adopts, ias, gas = _collect_inputs(eventlog)
    assert sm._criteria_met("S0", refs, evols, intros, adopts, ias, gas) is False


def test_memegraph_stage_shadow(monkeypatch, eventlog):
    # Append two stage transitions so the graph captures history
    eventlog.append(
        EventKinds.STAGE_UPDATE,
        "",
        {"from": "S0", "to": "S1", "reason": "bootstrap"},
    )
    eventlog.append(
        EventKinds.STAGE_UPDATE,
        "",
        {"from": "S1", "to": "S2", "reason": "progress"},
    )

    graph = MemeGraphProjection(eventlog)
    sm = StageManager(eventlog, graph)

    # Ensure the graph path is preferred when available
    from pmm.runtime import stage_manager as sm_module

    calls: list[str] = []

    def _fail_legacy(self):  # pragma: no cover - defensive guard
        calls.append("legacy")
        raise AssertionError(
            "legacy stage path should not be invoked when graph present"
        )

    monkeypatch.setattr(sm_module.StageManager, "_current_stage_legacy", _fail_legacy)
    sm_module.logger.setLevel(logging.INFO)

    assert sm.current_stage() == "S2"
    assert not calls
