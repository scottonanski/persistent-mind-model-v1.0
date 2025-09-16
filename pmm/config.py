# pmm/config.py
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass


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
    # Fixed cadence: background autonomy ticks every 10 seconds (no env override)
    autonomy_interval = 10.0
    # Truth-first evidence policy: artifact required (no env override)
    require_artifact_evidence = True
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

# Commitment Extractor Configuration (constants)
COMMITMENT_THRESHOLD = 0.70
DUPLICATE_SIM_THRESHOLD = 0.60

# Continuity Engine Configuration (constants)
CONTINUITY_REFLECTION_COOLDOWN_HOURS = 6
CONTINUITY_LOOKBACK_DAYS = 30
CONTINUITY_INSIGHT_CONFIDENCE_THRESHOLD = 0.70

# Prioritizer Configuration (constant)
PRIORITY_THRESHOLD = 0.70

# Debug Configuration (disabled in core)
DEBUG_MODE = False
