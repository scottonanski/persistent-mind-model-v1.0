from __future__ import annotations
import json
import time
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional

_TUNER_VERSION = "tuner.v1.0"
_DEFAULT_WINDOW = 200  # max recent samples per (model, task)
_HI_CUTOFF = 0.15  # if length-stop rate > 15% → scale up a bit
_LO_CUTOFF = 0.03  # if length-stop rate < 3% and under-using → scale down a bit
_UNDERUSE_FRAC = 0.60  # "under-use" if avg completion < 60% of target
_MAX_SCALE = 1.30
_MIN_SCALE = 0.80
_STEP = 0.05  # scale adjustments step


def _data_dir() -> Path:
    root = Path(os.getenv("PMM_DATA_DIR", ".data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Sample:
    t: float
    prompt: int
    target: int
    completion: int
    stop: str | None


@dataclass
class Bucket:
    # ring buffer is overkill; we'll just trim arrays
    samples: list[Sample]
    scale: float
    version: str


class AllocTuner:
    """
    Conservative, monotonic tuner:
      - Tracks recent stop_reason=length rate & utilization per (model, task)
      - Suggests a multiplicative scale in [0.80, 1.30] with 0.05 steps
      - Only adjusts when thresholds are clearly crossed
      - Fully persisted & versioned for reproducibility
    """

    def __init__(self, path: Optional[str] = None, window: int = _DEFAULT_WINDOW):
        self.window = max(50, int(window))
        self.path = Path(path) if path else _data_dir() / "alloc_tuner.json"
        self._buckets: Dict[str, Bucket] = {}
        self._load()

    def key(self, model_key: str, task: str) -> str:
        return f"{model_key}::{task}"

    # ---- Persistence ---------------------------------------------------------
    def _load(self):
        if self.path.exists():
            try:
                raw = json.load(open(self.path, "r"))
                for k, v in raw.items():
                    smps = [Sample(**s) for s in v.get("samples", [])]
                    self._buckets[k] = Bucket(
                        samples=smps,
                        scale=float(v.get("scale", 1.0)),
                        version=v.get("version", _TUNER_VERSION),
                    )
            except Exception:
                self._buckets = {}

    def _save(self):
        out = {}
        for k, b in self._buckets.items():
            out[k] = {
                "samples": [asdict(s) for s in b.samples],
                "scale": b.scale,
                "version": b.version,
            }
        with open(self.path, "w") as f:
            json.dump(out, f, indent=2, sort_keys=True)

    # ---- Public API ----------------------------------------------------------
    def get_scale(self, *, model_key: str, task: str) -> float:
        b = self._buckets.get(self.key(model_key, task))
        return float(b.scale) if b else 1.0

    def record(
        self,
        *,
        model_key: str,
        task: str,
        prompt_tokens: int,
        target_out: int,
        completion_tokens: int,
        stop_reason: str | None,
    ) -> float:
        k = self.key(model_key, task)
        b = self._buckets.get(k)
        if not b:
            b = Bucket(samples=[], scale=1.0, version=_TUNER_VERSION)
            self._buckets[k] = b

        b.samples.append(
            Sample(
                t=time.time(),
                prompt=prompt_tokens,
                target=target_out,
                completion=completion_tokens,
                stop=stop_reason,
            )
        )
        # Trim window
        if len(b.samples) > self.window:
            b.samples = b.samples[-self.window :]

        # Recompute suggestion only when we have a decent batch
        if len(b.samples) >= max(50, int(0.25 * self.window)):
            n = len(b.samples)
            cuts = sum(1 for s in b.samples if (s.stop or "") == "length")
            cutoff_rate = cuts / n
            avg_target = max(1, sum(s.target for s in b.samples) // n)
            avg_comp = sum(s.completion for s in b.samples) / n
            underuse = avg_comp < _UNDERUSE_FRAC * avg_target

            scale = b.scale
            if cutoff_rate > _HI_CUTOFF:
                scale = min(_MAX_SCALE, round((scale + _STEP) / _STEP) * _STEP)
            elif cutoff_rate < _LO_CUTOFF and underuse:
                scale = max(_MIN_SCALE, round((scale - _STEP) / _STEP) * _STEP)

            # Monotonic ratchet: only commit if changed
            if abs(scale - b.scale) >= 1e-9:
                b.scale = scale
                self._save()
        else:
            # Save occasionally to persist new keys
            self._save()

        return b.scale
