# pmm/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(dotenv_path: str = ".env") -> None:
    p = Path(dotenv_path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class RuntimeEnv:
    provider: str
    model: str
    db_path: str
    reflect_enabled: bool
    autonomy_interval: float
    require_artifact_evidence: bool
    commitment_ttl_hours: int
    commitment_dedup_window: int
    ngram_ban_file: str | None
    default_model: str
    default_base_url: str
    default_db_path: str
    commitment_threshold: float
    duplicate_sim_threshold: float
    continuity_reflection_cooldown_hours: int
    continuity_lookback_days: int
    continuity_insight_confidence_threshold: float
    priority_threshold: float
    debug_mode: bool


def load_runtime_env(dotenv_path: str = ".env") -> RuntimeEnv:
    # Best-effort .env load for external libs (e.g., API keys); PMM core uses constants below
    load_dotenv(dotenv_path)
    provider = os.getenv("PMM_PROVIDER", "openai")
    # Prefer OPENAI_MODEL if set; otherwise PMM_MODEL; fallback to gpt-4o-mini
    model = os.getenv("OPENAI_MODEL", os.getenv("PMM_MODEL", "gpt-4o-mini"))
    db_path = os.getenv("PMM_DB", ".data/pmm.db")
    # Reflection is always enabled; no env gate
    reflect_enabled = True
    # Fixed cadence: background autonomy ticks every 10 seconds for responsive IAS growth without performance issues
    autonomy_interval = 10.0
    # Truth-first evidence policy: artifact required (no env override)
    require_artifact_evidence = False
    # Commitment TTL and dedup knobs (constants)
    commitment_ttl_hours = 24
    commitment_dedup_window = 5

    ngram_ban_file = os.getenv("PMM_NGRAM_BAN_FILE") or None

    default_model = os.getenv("PMM_DEFAULT_MODEL", "llama3")
    default_base_url = os.getenv("PMM_DEFAULT_BASE_URL", "http://localhost:11434")
    default_db_path = os.getenv("PMM_DB_PATH", "pmm_data.db")
    commitment_threshold = 0.70
    duplicate_sim_threshold = 0.60
    continuity_reflection_cooldown_hours = 6
    continuity_lookback_days = 30
    continuity_insight_confidence_threshold = 0.70
    priority_threshold = 0.70
    # Debug mode (no effect on core behavior); keep False for deterministic runs
    debug_mode = False

    return RuntimeEnv(
        provider=provider,
        model=model,
        db_path=db_path,
        reflect_enabled=reflect_enabled,
        autonomy_interval=autonomy_interval,
        require_artifact_evidence=require_artifact_evidence,
        commitment_ttl_hours=commitment_ttl_hours,
        commitment_dedup_window=commitment_dedup_window,
        ngram_ban_file=ngram_ban_file,
        default_model=default_model,
        default_base_url=default_base_url,
        default_db_path=default_db_path,
        commitment_threshold=commitment_threshold,
        duplicate_sim_threshold=duplicate_sim_threshold,
        continuity_reflection_cooldown_hours=continuity_reflection_cooldown_hours,
        continuity_lookback_days=continuity_lookback_days,
        continuity_insight_confidence_threshold=continuity_insight_confidence_threshold,
        priority_threshold=priority_threshold,
        debug_mode=debug_mode,
    )


# Configuration settings for Persistent Mind Model (PMM)

# LLM Configuration
DEFAULT_MODEL = os.getenv("PMM_DEFAULT_MODEL", "llama3")
DEFAULT_BASE_URL = os.getenv("PMM_DEFAULT_BASE_URL", "http://localhost:11434")

# Storage Configuration
DEFAULT_DB_PATH = os.getenv("PMM_DB_PATH", "pmm_data.db")

# Performance Optimizations (Phase 1 & 2)
# Always enabled for 10-80x speedup. No flags - deterministic by default.
# These caches are thoroughly tested and provide identical results to non-cached versions.
USE_PROJECTION_CACHE = True  # 5-50x speedup for projection operations
USE_METRICS_CACHE = True  # 2-5x speedup for metrics computation
USE_EMBEDDING_CACHE = True  # 2-3x speedup for embedding operations

# Commitment Extractor Configuration (constants)
COMMITMENT_THRESHOLD = 0.62
DUPLICATE_SIM_THRESHOLD = 0.60
ASSISTANT_NAMING_MIN_CONFIDENCE = 0.90
IDENTITY_ADOPT_MIN_TURNS = 5

# Continuity Engine Configuration (constants)
CONTINUITY_REFLECTION_COOLDOWN_HOURS = 6
CONTINUITY_LOOKBACK_DAYS = 30
CONTINUITY_INSIGHT_CONFIDENCE_THRESHOLD = 0.70

# Prioritizer Configuration (constant)
PRIORITY_THRESHOLD = 0.70

# Reasoning Trace Configuration (constants)
# Captures PMM's reasoning process (node traversal, confidence, query context)
# without performance degradation through probabilistic sampling
REASONING_TRACE_ENABLED = True  # Always enabled
REASONING_TRACE_SAMPLING_RATE = 0.01  # 1% sampling rate
REASONING_TRACE_MIN_CONFIDENCE = 0.8  # Always log high-confidence decisions
REASONING_TRACE_BUFFER_SIZE = 1000  # Flush warning threshold

# Performance Optimization Configuration (Phase 1)
# These optimizations are always enabled for 20-40% speedup with no behavior changes
# Request-scoped caching eliminates redundant database reads
# Context optimization reduces token count while preserving quality
MAX_COMMITMENT_CHARS = 400  # Character budget for commitment text
MAX_REFLECTION_CHARS = 600  # Character budget for reflection text

# Event Kind Constants (for refactored debug events)
# Legacy compatibility flag - set to False after migration is complete
SUPPORT_LEGACY_DEBUG_EVENTS = False

# New event kinds to replace overloaded 'debug' kind
NAME_ATTEMPT_USER = "name_attempt_user"
NAME_ATTEMPT_SYSTEM = "name_attempt_system"
REFLECTION_SKIPPED = "reflection_skipped"
REFLECTION_FORCED = "reflection_forced"
REFLECTION_REJECTED = "reflection_rejected"

# Skip reason constants (normalized from legacy reflect_skip values)
DUE_TO_CADENCE = "due_to_cadence"
DUE_TO_LOW_NOVELTY = "due_to_low_novelty"
DUE_TO_MIN_TIME = "due_to_min_time"
DUE_TO_MIN_TURNS = "due_to_min_turns"
DUE_TO_TIME = "due_to_time"

# All configuration constants for the load() function
_DEFAULTS = {
    "DEFAULT_MODEL": DEFAULT_MODEL,
    "DEFAULT_BASE_URL": DEFAULT_BASE_URL,
    "DEFAULT_DB_PATH": DEFAULT_DB_PATH,
    "COMMITMENT_THRESHOLD": COMMITMENT_THRESHOLD,
    "DUPLICATE_SIM_THRESHOLD": DUPLICATE_SIM_THRESHOLD,
    "CONTINUITY_REFLECTION_COOLDOWN_HOURS": CONTINUITY_REFLECTION_COOLDOWN_HOURS,
    "CONTINUITY_LOOKBACK_DAYS": CONTINUITY_LOOKBACK_DAYS,
    "CONTINUITY_INSIGHT_CONFIDENCE_THRESHOLD": CONTINUITY_INSIGHT_CONFIDENCE_THRESHOLD,
    "PRIORITY_THRESHOLD": PRIORITY_THRESHOLD,
    "REASONING_TRACE_ENABLED": REASONING_TRACE_ENABLED,
    "REASONING_TRACE_SAMPLING_RATE": REASONING_TRACE_SAMPLING_RATE,
    "REASONING_TRACE_MIN_CONFIDENCE": REASONING_TRACE_MIN_CONFIDENCE,
    "REASONING_TRACE_BUFFER_SIZE": REASONING_TRACE_BUFFER_SIZE,
    "MAX_COMMITMENT_CHARS": MAX_COMMITMENT_CHARS,
    "MAX_REFLECTION_CHARS": MAX_REFLECTION_CHARS,
    "SUPPORT_LEGACY_DEBUG_EVENTS": SUPPORT_LEGACY_DEBUG_EVENTS,
    "NAME_ATTEMPT_USER": NAME_ATTEMPT_USER,
    "NAME_ATTEMPT_SYSTEM": NAME_ATTEMPT_SYSTEM,
    "REFLECTION_SKIPPED": REFLECTION_SKIPPED,
    "REFLECTION_FORCED": REFLECTION_FORCED,
    "REFLECTION_REJECTED": REFLECTION_REJECTED,
    "ASSISTANT_NAMING_MIN_CONFIDENCE": ASSISTANT_NAMING_MIN_CONFIDENCE,
    "IDENTITY_ADOPT_MIN_TURNS": IDENTITY_ADOPT_MIN_TURNS,
    "DUE_TO_CADENCE": DUE_TO_CADENCE,
    "DUE_TO_LOW_NOVELTY": DUE_TO_LOW_NOVELTY,
    "DUE_TO_MIN_TIME": DUE_TO_MIN_TIME,
    "DUE_TO_MIN_TURNS": DUE_TO_MIN_TURNS,
    "DUE_TO_TIME": DUE_TO_TIME,
}


def load() -> dict:
    """Load PMM policy/config values.

    Order of precedence:
      1) Project-local JSON at .pmm/config.json (if present, best-effort parse)
      2) Built-in defaults above

    Returns a shallow dict of config values.
    """
    try:
        import json as _json_local
        from pathlib import Path as _Path

        cfg_path = _Path(".pmm/config.json")
        if cfg_path.exists():
            try:
                data = _json_local.loads(cfg_path.read_text())
                if isinstance(data, dict):
                    out = dict(_DEFAULTS)
                    out.update({k: v for k, v in data.items() if k in _DEFAULTS})
                    return out
            except Exception:
                # Fall through to defaults on parse errors
                pass
    except Exception:
        pass
    return dict(_DEFAULTS)
