from __future__ import annotations

import sys
from typing import Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pmm.models import (
    list_available_models,
    get_default_model,
    get_model_config,
    AVAILABLE_MODELS,
    get_ollama_models,
)

"""Interactive model selection UI.

Separated from chat runtime to avoid mixing UI logic with core loop.
"""

console = Console()


def _print_menu() -> None:
    default_model = get_default_model()
    default_cfg = get_model_config(default_model)
    cost = (
        f"${default_cfg.cost_per_1k_tokens:.4f}/1K"
        if default_cfg.cost_per_1k_tokens > 0
        else "Free (local)"
    )

    title = Text("PMM Model Selection", style="bold blue")
    panel = Panel.fit(
        f"[bold cyan]CURRENT DEFAULT:[/] {default_model} ({default_cfg.provider})\n"
        f"{default_cfg.description}\n"
        f"Max tokens: {default_cfg.max_tokens:,} | Cost: {cost}",
        title=title,
        border_style="blue",
    )
    console.print(panel)
    console.print()

    # Create a table for available models
    table = Table(
        title="📋 Available Models", show_header=True, header_style="bold magenta"
    )
    table.add_column("#", style="cyan", justify="right", min_width=2)
    table.add_column("Model", style="cyan", no_wrap=True)
    table.add_column("Provider", style="green")
    table.add_column("Tokens", style="yellow", justify="right")
    table.add_column("Cost", style="red")
    table.add_column("Status", style="white")

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
        marker = "⭐ " if name == default_model else ""
        status = (
            "🟢"
            if cfg.provider == "ollama" and name in ollama_available_names
            else "🔴" if cfg.provider == "ollama" else ""
        )

        table.add_row(
            str(i), f"{marker}{name}", cfg.provider, f"{cfg.max_tokens:,}", cstr, status
        )

    console.print(table)
    console.print()

    instructions = Text("💡 Select a model:", style="bold yellow")
    console.print(instructions)
    console.print("   • Press ENTER to use current default")
    console.print(f"   • Type the number (1-{len(available)}) shown in the table above")
    console.print("   • Type the exact model name")
    console.print("   • Type 'list' to reprint this menu")
    console.print()


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
            choice = console.input("🎯 Your choice: ").strip()
            if choice.lower() == "list":
                _print_menu()
                continue
            resolved = _resolve(choice)
            if resolved:
                return resolved
            console.print(
                "❌ Unknown selection. Try again or type 'list'.", style="red"
            )
        except KeyboardInterrupt:
            console.print("\n👋 Cancelled.", style="yellow")
            return None
