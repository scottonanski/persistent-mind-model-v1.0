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


def load_runtime_env(dotenv_path: str = ".env") -> RuntimeEnv:
    load_dotenv(dotenv_path)
    provider = os.getenv("PMM_PROVIDER", "openai")
    # Prefer OPENAI_MODEL if set; otherwise PMM_MODEL; fallback to gpt-4o-mini
    model = os.getenv("OPENAI_MODEL", os.getenv("PMM_MODEL", "gpt-4o-mini"))
    db_path = os.getenv("PMM_DB", ".data/pmm.db")
    reflect_enabled = os.getenv("PMM_REFLECT", "1") not in {"0", "false", "False"}
    return RuntimeEnv(
        provider=provider, model=model, db_path=db_path, reflect_enabled=reflect_enabled
    )
