from __future__ import annotations

import pytest

from pmm.runtime.cooldown import ReflectionCooldown
from pmm.runtime.evolution_kernel import EvolutionKernel
from pmm.runtime.policy.evolution import DEFAULT_POLICY
from pmm.runtime.traits import normalize_key


class FakeEventLog:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def read_tail(self, limit: int = 1000) -> list[dict]:
        return self.events[-limit:]

    def read_all(self) -> list[dict]:
        return list(self.events)

    def append(self, kind: str, content: str, meta: dict | None = None) -> int:
        eid = len(self.events) + 1
        self.events.append(
            {"id": eid, "kind": kind, "content": content, "meta": meta or {}}
        )
        return eid


class FakeTracker:
    def __init__(self) -> None:
        self._open_map: dict[str, dict] = {}

    def set_open_map(self, mapping: dict[str, dict]) -> None:
        self._open_map = mapping

    def _open_map_all(self, _events: list[dict]) -> dict[str, dict]:
        return self._open_map


class FakeCooldown(ReflectionCooldown):
    def __init__(self) -> None:
        super().__init__()

    def should_reflect(self, now: float, novelty: float):  # type: ignore[override]
        return True, "test_force"


class KernelTestEnv:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pmm.runtime import evolution_kernel as ek_module

        self.eventlog = FakeEventLog()
        self.tracker = FakeTracker()
        self.cooldown = FakeCooldown()
        self.traits: dict[str, float] = {normalize_key("conscientiousness"): 0.5}
        self.ias = DEFAULT_POLICY.ias_threshold + 0.1
        self.gas = DEFAULT_POLICY.gas_threshold + 0.1

        def _fake_build_identity(_events: list[dict]) -> dict:
            return {"name": "Test", "traits": dict(self.traits)}

        def _fake_build_self_model(_events: list[dict], eventlog=None) -> dict:
            return {"identity": {"name": "Test", "traits": dict(self.traits)}}

        def _fake_metrics(_eventlog) -> tuple[float, float]:
            return float(self.ias), float(self.gas)

        monkeypatch.setattr(ek_module, "build_identity", _fake_build_identity)
        monkeypatch.setattr(ek_module, "build_self_model", _fake_build_self_model)
        monkeypatch.setattr(ek_module, "get_or_compute_ias_gas", _fake_metrics)

        self.kernel = EvolutionKernel(self.eventlog, self.tracker, self.cooldown)

    def seed_commitments(self, opens: int, closes: int) -> None:
        self.eventlog.events = []
        for idx in range(opens):
            cid = f"c{idx}"
            self.eventlog.append("commitment_open", "", {"cid": cid})
            if idx < closes:
                self.eventlog.append("commitment_close", "", {"cid": cid})

    def set_open_commitments(self, count: int) -> None:
        mapping = {f"open{idx}": {"text": f"Commitment {idx}"} for idx in range(count)}
        self.tracker.set_open_map(mapping)


@pytest.fixture
def kernel_env(monkeypatch: pytest.MonkeyPatch) -> KernelTestEnv:
    return KernelTestEnv(monkeypatch)


def test_trait_target_when_closure_extremes(kernel_env: KernelTestEnv) -> None:
    key = normalize_key("conscientiousness")
    kernel_env.traits[key] = 0.5
    kernel_env.set_open_commitments(3)

    kernel_env.seed_commitments(opens=40, closes=36)
    result_hi = kernel_env.kernel.evaluate_identity_evolution(
        events=kernel_env.eventlog.events
    )
    assert key in result_hi["trait_adjustments"]
    target_hi = result_hi["trait_adjustments"][key]["target"]
    expected_hi = min(1.0, 0.5 + DEFAULT_POLICY.conscientiousness_delta_high)
    assert target_hi == pytest.approx(expected_hi, rel=1e-6)

    kernel_env.seed_commitments(opens=40, closes=4)
    result_lo = kernel_env.kernel.evaluate_identity_evolution(
        events=kernel_env.eventlog.events
    )
    assert key in result_lo["trait_adjustments"]
    target_lo = result_lo["trait_adjustments"][key]["target"]
    expected_lo = max(0.0, 0.5 + DEFAULT_POLICY.conscientiousness_delta_low)
    assert target_lo == pytest.approx(expected_lo, rel=1e-6)


def test_reflection_targets_summary_present(kernel_env: KernelTestEnv) -> None:
    key = normalize_key("conscientiousness")
    kernel_env.traits[key] = 0.55
    kernel_env.set_open_commitments(DEFAULT_POLICY.open_commitments_threshold + 2)
    kernel_env.seed_commitments(opens=30, closes=26)
    kernel_env.ias = DEFAULT_POLICY.ias_threshold - 0.1
    reflection_id = kernel_env.kernel.trigger_reflection_if_needed(
        events=kernel_env.eventlog.events
    )
    assert reflection_id is not None
    meta = kernel_env.eventlog.events[-1]["meta"]
    assert "targets_summary" in meta
    summary = meta["targets_summary"]
    if summary:
        parts = [segment.strip() for segment in summary.split(",") if segment.strip()]
        assert all(":" in part for part in parts)


def test_proposal_shape_lowercase(kernel_env: KernelTestEnv) -> None:
    key = normalize_key("conscientiousness")
    kernel_env.traits[key] = 0.45
    kernel_env.set_open_commitments(4)
    kernel_env.seed_commitments(opens=25, closes=22)
    proposal = kernel_env.kernel.propose_identity_adjustment(
        events=kernel_env.eventlog.events
    )
    assert proposal is not None
    assert "traits" in proposal
    assert proposal["traits"]
    for trait_key, value in proposal["traits"].items():
        assert trait_key == trait_key.lower()
        assert 0.0 <= value <= 1.0
