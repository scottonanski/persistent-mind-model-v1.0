"""Model registry and discovery utilities.

This module keeps model parsing and selection data out of the CLI logic.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class ModelConfig:
    name: str
    provider: str  # "openai" | "ollama"
    max_tokens: int = 4096
    temperature: float = 0.7
    cost_per_1k_tokens: float = 0.0
    description: str = ""


def _run_ollama_list(timeout: int = 5) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def check_ollama_running() -> bool:
    """Return True if `ollama list` succeeds quickly; False otherwise."""
    proc = _run_ollama_list(timeout=5)
    return bool(proc and proc.returncode == 0)


def check_ollama_python_library() -> bool:
    """Return True if the Python ollama library is available for import."""
    import importlib.util

    return importlib.util.find_spec("ollama") is not None


def get_ollama_models() -> list[dict]:
    """Parse `ollama list` output into a list of {name,size,full_line} dicts.

    Returns an empty list if Ollama is not installed/running or if the Python
    ollama library is not available.
    """
    # First check if the Python library is available
    if not check_ollama_python_library():
        return []

    proc = _run_ollama_list(timeout=10)
    if not proc or proc.returncode != 0:
        return []
    out = proc.stdout or ""
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return []
    # Skip header if present (first line usually: NAME ID SIZE ...)
    body = lines[1:] if len(lines) > 1 else []
    models: list[dict] = []
    for ln in body:
        parts = ln.split()
        if not parts:
            continue
        name = parts[0]
        size = parts[2] if len(parts) > 2 else "Unknown"
        models.append({"name": name, "size": size, "full_line": ln.strip()})
    return models


def build_dynamic_models() -> dict[str, ModelConfig]:
    """Seed OpenAI models and append detected Ollama models if available."""
    models: dict[str, ModelConfig] = {
        # OpenAI: curated entries (no network call)
        "gpt-4o-mini": ModelConfig(
            name="gpt-4o-mini",
            provider="openai",
            max_tokens=16384,
            temperature=0.7,
            cost_per_1k_tokens=0.00015,
            description="Fast, cost-effective model for most PMM tasks",
        ),
        "gpt-4o": ModelConfig(
            name="gpt-4o",
            provider="openai",
            max_tokens=128000,
            temperature=0.7,
            cost_per_1k_tokens=0.005,
            description="High-quality model for complex reasoning",
        ),
        "gpt-3.5-turbo": ModelConfig(
            name="gpt-3.5-turbo",
            provider="openai",
            max_tokens=4096,
            temperature=0.7,
            cost_per_1k_tokens=0.0015,
            description="Legacy model, still capable",
        ),
    }

    for info in get_ollama_models():
        mname = info.get("name")
        if not mname:
            continue
        models[mname] = ModelConfig(
            name=mname,
            provider="ollama",
            max_tokens=4096,
            temperature=0.7,
            cost_per_1k_tokens=0.0,
            description=f"Local Ollama model ({info.get('size','?')})",
        )
    return models


# Build once at import (fast, local-only). Callers can re-run build_dynamic_models if needed.
AVAILABLE_MODELS: dict[str, ModelConfig] = build_dynamic_models()


def list_available_models() -> list[str]:
    return list(AVAILABLE_MODELS.keys())


def get_default_model() -> str:
    return os.getenv("PMM_DEFAULT_MODEL", "gpt-4o-mini")


def get_model_config(model_name: str | None = None) -> ModelConfig:
    name = model_name or get_default_model()
    if name not in AVAILABLE_MODELS:
        # fallback to known-good
        name = "gpt-4o-mini"
    return AVAILABLE_MODELS[name]


def get_models_by_provider(provider: str) -> list[str]:
    return [n for n, cfg in AVAILABLE_MODELS.items() if cfg.provider == provider]
