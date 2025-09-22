from __future__ import annotations
from .alloc_log import read_latest
from .alloc_tuner import AllocTuner


def summarize(n: int = 200) -> dict:
    rows = read_latest(n)
    by_key = {}
    for r in rows:
        key = f"{r.get('model_key')}::{r.get('task')}"
        s = by_key.setdefault(
            key, {"calls": 0, "length_stops": 0, "avg_target": 0, "avg_comp": 0.0}
        )
        s["calls"] += 1
        s["length_stops"] += 1 if r.get("stop_reason") == "length" else 0
        s["avg_target"] += int(r.get("target_out") or 0)
        s["avg_comp"] += int(r.get("completion_tokens") or 0)
    for k, s in by_key.items():
        if s["calls"]:
            s["avg_target"] //= s["calls"]
            s["avg_comp"] = round(s["avg_comp"] / s["calls"], 1)
            s["cutoff_rate"] = round(s["length_stops"] / s["calls"], 3)
    # include current tuner scales
    t = AllocTuner()
    scales = {}
    for k in by_key.keys():
        model, task = k.split("::", 1)
        scales[k] = t.get_scale(model_key=model, task=task)
    return {"summary": by_key, "scales": scales}
