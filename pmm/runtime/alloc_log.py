from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

_FILENAME = "alloc_log.jsonl"


def _path() -> Path:
    root = Path(os.getenv("PMM_DATA_DIR", ".data"))
    root.mkdir(parents=True, exist_ok=True)
    return root / _FILENAME


def log_alloc(event: Dict[str, Any]) -> None:
    """
    Append a single JSON line. Non-fatal on error.
    Expected keys (suggested): ts, model_key, task, prompt_tokens, target_out,
      completion_tokens, stop_reason, tuner_scale, caps_source, caps_max_ctx, caps_max_out_hint, policy_id, notes
    """
    try:
        event = dict(event)
        event.setdefault("ts", time.time())
        with open(_path(), "a") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception:
        pass


def read_latest(n: int = 100) -> list[dict]:
    try:
        p = _path()
        if not p.exists():
            return []
        # Read efficiently from end
        lines = p.read_text().splitlines()
        return [json.loads(x) for x in lines[-max(1, int(n)) :]]
    except Exception:
        return []
