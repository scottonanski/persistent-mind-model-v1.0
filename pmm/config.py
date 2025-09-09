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


def load_runtime_env(dotenv_path: str = ".env") -> RuntimeEnv:
    load_dotenv(dotenv_path)
    provider = os.getenv("PMM_PROVIDER", "openai")
    # Prefer OPENAI_MODEL if set; otherwise PMM_MODEL; fallback to gpt-4o-mini
    model = os.getenv("OPENAI_MODEL", os.getenv("PMM_MODEL", "gpt-4o-mini"))
    db_path = os.getenv("PMM_DB", ".data/pmm.db")
    reflect_enabled = os.getenv("PMM_REFLECT", "1") not in {"0", "false", "False"}
    try:
        autonomy_interval = float(os.getenv("PMM_AUTONOMY_INTERVAL", "0"))
    except ValueError:
        autonomy_interval = 0.0
    require_artifact_evidence = os.getenv("PMM_REQUIRE_ARTIFACT_EVIDENCE", "0") in {
        "1",
        "true",
        "True",
    }
    # Commitment TTL and dedup knobs
    try:
        commitment_ttl_hours = int(os.getenv("PMM_COMMITMENT_TTL_HOURS", "24"))
    except ValueError:
        commitment_ttl_hours = 24
    try:
        commitment_dedup_window = int(os.getenv("PMM_COMMITMENT_DEDUP_WINDOW", "5"))
    except ValueError:
        commitment_dedup_window = 5

    ngram_ban_file = os.getenv("PMM_NGRAM_BAN_FILE") or None

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
    )
