from __future__ import annotations

import statistics
import time

import pmm.runtime.loop as loop_mod
from pmm.llm.factory import LLMConfig
from pmm.runtime import self_evolution as _self_evolution
from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.eventlog import EventLog
from pmm.runtime.loop import AutonomyLoop, Runtime


class NoOpKernel:
    def evaluate_identity_evolution(self, **_):
        return {
            "trait_adjustments": {
                "conscientiousness": {"target": 0.62},
            },
            "reflection_needed": False,
        }

    def propose_identity_adjustment(self, **_):
        return {
            "traits": {"conscientiousness": 0.62},
            "context": {"note": "stable"},
            "reason": "test",
        }


class BusyKernel:
    def evaluate_identity_evolution(self, **_):
        return {
            "trait_adjustments": {
                "conscientiousness": {"target": 0.62},
            },
            "reflection_needed": True,
        }

    def propose_identity_adjustment(self, **_):
        return {
            "traits": {"conscientiousness": 0.62},
            "context": {"note": "stable"},
            "reason": "test",
        }


def _make_runtime(db_path) -> Runtime:
    cfg = LLMConfig(provider="dummy", model="noop")
    eventlog = EventLog(str(db_path))
    rt = Runtime(cfg, eventlog)
    rt.cooldown = ReflectionCooldown()
    rt.reflect = lambda _context: ""
    return rt


def _median_tick_ms(rt: Runtime, kernel, *, reps: int = 5, warmups: int = 2) -> float:
    rt.evolution_kernel = kernel
    loop = AutonomyLoop(
        eventlog=rt.eventlog,
        cooldown=rt.cooldown,
        interval_seconds=0.01,
        runtime=rt,
    )
    for _ in range(warmups):
        loop.tick()
    samples: list[float] = []
    for _ in range(reps):
        t0 = time.perf_counter()
        loop.tick()
        t1 = time.perf_counter()
        samples.append((t1 - t0) * 1000.0)
    return statistics.median(samples)


def test_autonomy_tick_overhead_under_15_percent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        _self_evolution.SelfEvolution,
        "apply_policies",
        staticmethod(lambda events, metrics: ({}, "stub")),
    )

    monkeypatch.setattr(loop_mod, "emit_reflection", lambda *a, **k: 0)
    monkeypatch.setattr(loop_mod, "maybe_reflect", lambda *a, **k: (True, "stub"))
    monkeypatch.setattr(loop_mod._io, "append_name_attempt_user", lambda *a, **k: None)
    monkeypatch.setattr(loop_mod._io, "append_reflection_forced", lambda *a, **k: None)

    try:
        import pmm.runtime.semantic.semantic_growth as semantic_growth
    except ImportError:  # pragma: no cover - module optional
        semantic_growth = None
    if semantic_growth is not None:

        class _StubGrowth:
            def analyze_texts(self, texts):
                return {"total_texts": len(texts)}

            def detect_growth_paths(self, _analysis):
                return []

            def maybe_emit_growth_report(self, *args, **kwargs):
                return None

        monkeypatch.setattr(semantic_growth, "SemanticGrowth", _StubGrowth)

    baseline_rt = _make_runtime(tmp_path / "baseline-perf.db")
    stressed_rt = _make_runtime(tmp_path / "stressed-perf.db")

    baseline = _median_tick_ms(baseline_rt, NoOpKernel(), reps=5, warmups=3)
    stressed = _median_tick_ms(stressed_rt, BusyKernel(), reps=5, warmups=3)

    overhead_pct = (stressed - baseline) / max(baseline, 1e-6) * 100.0
    assert (
        overhead_pct < 15.0
    ), f"overhead {overhead_pct:.2f}% >= 15% (baseline {baseline:.2f} ms, stressed {stressed:.2f} ms)"
