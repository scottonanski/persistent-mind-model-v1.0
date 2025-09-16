"""Interactive model selection UI.

Separated from chat runtime to avoid mixing UI logic with core loop.
"""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from pmm.models import (
    list_available_models,
    get_default_model,
    get_model_config,
    AVAILABLE_MODELS,
    get_ollama_models,
)


def _print_menu() -> None:
    default_model = get_default_model()
    default_cfg = get_model_config(default_model)
    cost = (
        f"${default_cfg.cost_per_1k_tokens:.4f}/1K"
        if default_cfg.cost_per_1k_tokens > 0
        else "Free (local)"
    )
    print("=== PMM Model Selection ===")
    print()
    print(f"⭐ CURRENT DEFAULT: {default_model} ({default_cfg.provider})")
    print(f"   {default_cfg.description}")
    print(f"   Max tokens: {default_cfg.max_tokens:,} | Cost: {cost}")
    print()

    print("📋 Available Models:")
    available = list_available_models()
    # compute quick ollama availability map once
    try:
        ollama_available_names = {m["name"] for m in get_ollama_models()}
    except Exception:
        ollama_available_names = set()

    for i, name in enumerate(available, 1):
        cfg = AVAILABLE_MODELS[name]
        cstr = (
            f"${cfg.cost_per_1k_tokens:.4f}/1K"
            if cfg.cost_per_1k_tokens > 0
            else "Free (local)"
        )
        marker = "⭐" if name == default_model else f"{i:2d}."
        status = ""
        if cfg.provider == "ollama":
            status = " 🟢" if name in ollama_available_names else " 🔴"
        print(f"{marker} {name} ({cfg.provider}){status}")
        print(f"    {cfg.description}")
        print(f"    Max tokens: {cfg.max_tokens:,} | Cost: {cstr}")
        print()

    print("💡 Select a model:")
    print("   • Press ENTER to use current default")
    print(f"   • Type model number (1-{len(available)}) or exact model name")
    print("   • Type 'list' to reprint this menu")
    print()


def select_model(force_tty: bool = True) -> Optional[Tuple[str, str]]:
    """Return (provider, model_name) or None if cancelled.

    If stdin is not a TTY and force_tty is True, attempts to open /dev/tty.
    """
    _print_menu()
    available = list_available_models()

    def _resolve(choice: str) -> Optional[Tuple[str, str]]:
        if not choice:
            m = get_default_model()
            cfg = get_model_config(m)
            return (cfg.provider, cfg.name)
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(available):
                name = available[idx - 1]
                cfg = get_model_config(name)
                return (cfg.provider, cfg.name)
            return None
        if choice in available:
            cfg = get_model_config(choice)
            return (cfg.provider, cfg.name)
        return None

    if not sys.stdin.isatty() and force_tty:
        try:
            with open("/dev/tty", "r+") as tty:
                while True:
                    tty.write("🎯 Your choice: ")
                    tty.flush()
                    choice = tty.readline().strip()
                    if choice.lower() == "list":
                        _print_menu()
                        continue
                    resolved = _resolve(choice)
                    if resolved:
                        prov, name = resolved
                        tty.write(f"✅ Selected: {name} ({prov})\n")
                        tty.flush()
                        return resolved
                    tty.write(
                        "❌ Unknown selection. Try again or press ENTER for default.\n"
                    )
                    tty.flush()
        except Exception:
            # Fallback to default silently in non-interactive contexts
            m = get_default_model()
            cfg = get_model_config(m)
            return (cfg.provider, cfg.name)

    while True:
        try:
            choice = input("🎯 Your choice: ").strip()
            if choice.lower() == "list":
                _print_menu()
                continue
            resolved = _resolve(choice)
            if resolved:
                return resolved
            print("❌ Unknown selection. Try again or type 'list'.")
        except KeyboardInterrupt:
            print("\n👋 Cancelled.")
            return None
