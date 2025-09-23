# pmm/cli/chat.py
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pmm.cli.model_select import select_model
from pmm.config import load_runtime_env
from pmm.llm.factory import LLMConfig
from pmm.runtime.loop import Runtime, maybe_reflect as runtime_maybe_reflect
from pmm.runtime.metrics_view import MetricsView, humanize_reflect_reason
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity

logger = logging.getLogger(__name__)


def should_print_identity_notice(events: list[dict]) -> bool:
    """Return True if the first response after an identity adoption should show a banner."""

    last_adopt_id = None
    resp_ids: list[int] = []
    for ev in reversed(events):
        kind = ev.get("kind")
        if kind == "identity_adopt" and last_adopt_id is None:
            last_adopt_id = int(ev.get("id") or 0)
        if kind == "response":
            rid = ev.get("id")
            if isinstance(rid, int):
                resp_ids.append(rid)
        if last_adopt_id is not None and len(resp_ids) >= 2:
            break
    if last_adopt_id is None or not resp_ids:
        return False
    last_resp_id = resp_ids[0]
    prev_resp_id = resp_ids[1] if len(resp_ids) >= 2 else None
    if prev_resp_id is None or int(prev_resp_id) < int(last_adopt_id):
        return int(last_adopt_id) <= int(last_resp_id)
    return False


def _configure_logging(log_console: Console) -> None:
    handler = RichHandler(
        console=log_console,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
        omit_repeated_times=False,
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _system_panel(
    message: str, *, title: str = "system", border_style: str = "cyan"
) -> Panel:
    text = Text.from_markup(message.strip() if message else "")
    return Panel.fit(
        text,
        title=f"[{border_style}]{title.upper()}[/]",
        border_style=border_style,
        padding=(0, 1),
    )


def _render_assistant(console: Console, reply: str) -> None:
    content = (reply or "").rstrip()
    if not content:
        return
    try:
        body = Markdown(content, code_theme="monokai", justify="left")
    except Exception:
        body = Text(content)
    panel = Panel.fit(
        body,
        title="[green]ASSISTANT[/]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(panel)


def _metrics_panel(snap: dict) -> Panel:
    telemetry = snap.get("telemetry", {})
    ias = float(telemetry.get("IAS", 0.0))
    gas = float(telemetry.get("GAS", 0.0))
    stage = str(snap.get("stage", "none"))
    reflect_skip_raw = snap.get("reflect_skip", "none")
    reflect_skip = (
        humanize_reflect_reason(reflect_skip_raw)
        if str(reflect_skip_raw) != "none"
        else "none"
    )
    open_commitments = snap.get("open_commitments", {})
    open_count = int(open_commitments.get("count", 0))
    identity = snap.get("identity", {})
    name = identity.get("name") or "—"
    top_traits = identity.get("top_traits", [])
    priority = snap.get("priority_top5", [])
    self_lines = snap.get("self_model_lines") or []

    grid = Table.grid(expand=False, padding=(0, 1))
    summary = Text()
    summary.append("IAS ", style="bright_cyan")
    summary.append(f"{ias:.3f}", style="bold white")
    summary.append("   GAS ", style="bright_cyan")
    summary.append(f"{gas:.3f}", style="bold white")
    summary.append("   Stage ", style="bright_cyan")
    summary.append(stage, style="bold white")
    grid.add_row(summary)

    if reflect_skip != "none":
        line = Text("Reflection gate ", style="yellow")
        line.append(reflect_skip, style="bold white")
        grid.add_row(line)

    oc_line = Text("Open commitments ", style="bright_blue")
    oc_line.append(str(open_count), style="bold white")
    grid.add_row(oc_line)

    ident_line = Text("Identity ", style="green")
    ident_line.append(name, style="bold white")
    if top_traits:
        trait_parts = ", ".join(
            f"{t['trait']} {t['v']:.2f}" for t in top_traits if isinstance(t, dict)
        )
        if trait_parts:
            ident_line.append("   Traits ", style="green")
            ident_line.append(trait_parts, style="bold white")
    grid.add_row(ident_line)

    # Full OCEAN vector
    traits_full = identity.get("traits_full", {})
    if traits_full:
        tf_line = Text("OCEAN ", style="green")
        tf_line.append(
            f"O {traits_full.get('O','0.00')}  C {traits_full.get('C','0.00')}  E {traits_full.get('E','0.00')}  A {traits_full.get('A','0.00')}  N {traits_full.get('N','0.00')}",
            style="bold white",
        )
        grid.add_row(tf_line)

    if priority:
        pr_line = Text("Priority ", style="magenta")
        items: list[str] = []
        for item in priority[:5]:
            cid = str(item.get("cid") or "?")
            score = item.get("score")
            try:
                score_str = f"{float(score):.2f}"
            except Exception:
                score_str = "?"
            items.append(f"{cid} {score_str}")
        pr_line.append(" | ".join(items), style="bold white")
        grid.add_row(pr_line)

    if self_lines:
        grid.add_row(Text("", style="dim"))
        for ln in self_lines:
            grid.add_row(Text(str(ln), style="dim"))

    return Panel(
        grid,
        title="[blue]METRICS[/]",
        border_style="blue",
        padding=(0, 1),
        box=box.ROUNDED,
    )


def main() -> None:
    assistant_console = Console(highlight=False)
    log_console = Console(stderr=True, highlight=False)
    _configure_logging(log_console)

    env = load_runtime_env(".env")
    Path(env.db_path).parent.mkdir(parents=True, exist_ok=True)

    assistant_console.print(
        _system_panel(
            "🚀 Welcome to PMM! Please select your model.",
            title="welcome",
            border_style="blue",
        )
    )
    selection = select_model()
    if not selection:
        assistant_console.print(
            _system_panel("Cancelled. Exiting.", title="goodbye", border_style="yellow")
        )
        return

    provider, model_name = selection
    logger.info("[bold cyan]starting[/] PMM with %s (%s)", model_name, provider)

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "[bold red]OPENAI_API_KEY not set in environment (.env). Exiting.[/]"
        )
        sys.exit(2)

    eventlog = EventLog(env.db_path)
    cfg = LLMConfig(
        provider=provider, model=model_name, embed_provider=None, embed_model=None
    )

    ngram_bans = None
    if env.ngram_ban_file:
        try:
            path_ngram = Path(env.ngram_ban_file)
            if path_ngram.exists():
                ngram_bans = [
                    line.strip()
                    for line in path_ngram.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
        except Exception:
            ngram_bans = None

    runtime = Runtime(cfg, eventlog, ngram_bans=ngram_bans)
    metrics_view = MetricsView()

    runtime.start_autonomy(max(0.01, float(env.autonomy_interval or 10)))

    assistant_console.print(
        _system_panel(
            f"PMM ready ({provider}/{model_name}) — DB: {env.db_path}. Ctrl+C to exit.",
            title="ready",
            border_style="blue",
        )
    )

    try:
        logger.info(
            "[bold blue]autonomy[/] ON — ticks every %ss",
            int(env.autonomy_interval or 10),
        )
        logger.info(
            "[bold blue]reflection[/] ON — acceptance/cadence gates applied deterministically."
        )
    except Exception:
        pass

    try:
        while True:
            user_input = assistant_console.input("[bold blue]> [/] ").strip()
            if not user_input:
                continue

            normalized = user_input.strip()
            if normalized in {"--@metrics on", "--@metrics off"}:
                assistant_console.print(
                    _system_panel(
                        "Metrics view is always on in this build.",
                        title="metrics",
                        border_style="cyan",
                    )
                )
                continue

            if normalized == "--@models":
                assistant_console.print(
                    _system_panel(
                        "🔄 Model Selection", title="models", border_style="blue"
                    )
                )
                selection = select_model(force_tty=False)
                if selection:
                    new_provider, new_model = selection
                    logger.info(
                        "[bold cyan]switching[/] to %s (%s)", new_model, new_provider
                    )
                    runtime.set_model(new_provider, new_model)
                    assistant_console.print(
                        _system_panel(
                            "Model switched successfully.",
                            title="models",
                            border_style="green",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Model selection cancelled.",
                            title="models",
                            border_style="yellow",
                        )
                    )
                continue

            if normalized.lower() in {"exit", "quit", "/q"}:
                assistant_console.print(
                    _system_panel("bye.", title="goodbye", border_style="blue")
                )
                try:
                    runtime.stop_autonomy()
                except Exception:
                    pass
                return

            reply = runtime.handle_user(user_input)
            _render_assistant(assistant_console, reply)

            try:
                events = runtime.eventlog.read_all()
                if not hasattr(main, "_last_stage_label"):
                    setattr(main, "_last_stage_label", None)
                if not hasattr(main, "_last_cooldown_thr"):
                    setattr(main, "_last_cooldown_thr", None)

                stage_label = None
                for event in reversed(events):
                    if event.get("kind") == "stage_update":
                        stage_label = (event.get("meta") or {}).get("to")
                        break
                    if event.get("kind") == "policy_update":
                        meta = event.get("meta") or {}
                        if str(meta.get("component")) == "reflection":
                            stage_label = meta.get("stage") or stage_label
                            if stage_label:
                                break
                prev_stage_label = getattr(main, "_last_stage_label")
                if stage_label and stage_label != prev_stage_label:
                    logger.info(
                        "[bold blue][stage][/bold blue] %s → %s (cadence updated)",
                        prev_stage_label or "—",
                        stage_label,
                    )
                    setattr(main, "_last_stage_label", stage_label)

                cooldown_thr = None
                for event in reversed(events):
                    if event.get("kind") != "policy_update":
                        continue
                    meta = event.get("meta") or {}
                    if str(meta.get("component")) != "cooldown":
                        continue
                    params = meta.get("params") or {}
                    if "novelty_threshold" in params:
                        try:
                            cooldown_thr = float(params.get("novelty_threshold"))
                        except Exception:
                            cooldown_thr = None
                        break
                prev_thr = getattr(main, "_last_cooldown_thr")
                if cooldown_thr is not None and cooldown_thr != prev_thr:
                    logger.info(
                        "[bold blue][policy][/bold blue] cooldown.novelty_threshold → %.2f",
                        cooldown_thr,
                    )
                    setattr(main, "_last_cooldown_thr", cooldown_thr)
            except Exception:
                pass

            try:
                events = runtime.eventlog.read_all()
                last_event = events[-1] if events else None
                if last_event and last_event.get("kind") == "commitment_open":
                    meta = last_event.get("meta") or {}
                    if meta.get("reason") == "reflection":
                        if not hasattr(main, "_last_commitment_id"):
                            setattr(main, "_last_commitment_id", None)
                        prev_cid = getattr(main, "_last_commitment_id")
                        if last_event.get("id") != prev_cid:
                            logger.info(
                                "[bold blue][commitment][/bold blue] opened from reflection"
                            )
                            setattr(main, "_last_commitment_id", last_event.get("id"))
            except Exception:
                pass

            try:
                events = runtime.eventlog.read_all()
                if not hasattr(main, "_last_bridge_policy_id"):
                    setattr(main, "_last_bridge_policy_id", None)
                last_bridge_printed = getattr(main, "_last_bridge_policy_id")
                for event in reversed(events):
                    if event.get("kind") != "policy_update":
                        continue
                    meta = event.get("meta") or {}
                    src = meta.get("src_id")
                    if src is None:
                        continue
                    eid = int(event.get("id") or 0)
                    if eid and eid != last_bridge_printed:
                        logger.info(
                            "[bold blue][bridge][/bold blue] CurriculumUpdate→PolicyUpdate (pu_id=%s, src_id=%s)",
                            eid,
                            src,
                        )
                        setattr(main, "_last_bridge_policy_id", eid)
                    break
            except Exception:
                pass

            try:
                events = runtime.eventlog.read_all()
                if not hasattr(main, "_printed_reminder_ids"):
                    setattr(main, "_printed_reminder_ids", set())
                printed = getattr(main, "_printed_reminder_ids")
                for event in events:
                    if event.get("kind") != "commitment_reminder":
                        continue
                    eid = int(event.get("id") or 0)
                    if eid in printed:
                        continue
                    cid = (event.get("meta") or {}).get("cid")
                    if cid:
                        logger.warning(
                            "[bold yellow][reminder][/bold yellow] Commitment #%s is due!",
                            cid,
                        )
                        printed.add(eid)
            except Exception:
                pass

            try:
                events = runtime.eventlog.read_all()
                if should_print_identity_notice(events):
                    ident = build_identity(events)
                    name = ident.get("name")
                    if name:
                        logger.info(
                            "[bold blue][identity][/bold blue] adopted name: %s",
                            name,
                        )
            except Exception:
                pass

            try:
                snapshot = metrics_view.snapshot(runtime.eventlog)
                assistant_console.print(_metrics_panel(snapshot))
            except Exception:
                pass

            try:
                runtime_maybe_reflect(
                    runtime.eventlog,
                    runtime.cooldown,
                    llm_generate=lambda context: runtime.reflect(context),
                )
            except Exception:
                pass
    except (EOFError, KeyboardInterrupt):
        assistant_console.print(
            _system_panel("bye.", title="goodbye", border_style="blue")
        )
        try:
            runtime.stop_autonomy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
