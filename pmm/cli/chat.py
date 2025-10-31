# pmm/cli/chat.py
from __future__ import annotations

import logging
import os
import sys
import termios
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
from pmm.runtime.ledger_mirror import LedgerMirror
from pmm.runtime.loop import Runtime
from pmm.runtime.loop import maybe_reflect as runtime_maybe_reflect
from pmm.runtime.metrics_view import MetricsView, humanize_reflect_reason
from pmm.runtime.profiler import get_global_profiler
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_identity

logger = logging.getLogger(__name__)
failures_logger = logging.getLogger("pmm.cli.failures")

profiler = get_global_profiler()


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
    # Set to WARNING by default for cleaner chat output
    # Users can enable verbose logging with --@metrics logs on
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pmm.runtime.metrics").setLevel(logging.WARNING)
    logging.getLogger("pmm.llm.adapters.ollama_chat").setLevel(logging.WARNING)
    logging.getLogger("pmm.runtime.trace_buffer").setLevel(logging.WARNING)
    logging.getLogger("pmm.runtime.profiler").setLevel(
        logging.ERROR
    )  # Hide slow operation warnings
    logging.getLogger("pmm.cli.failures").setLevel(logging.ERROR)


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


def _show_status(console: Console, message: str) -> None:
    """Show a status message that can be cleared."""
    console.print(f"[dim cyan]{message}[/dim cyan]")


def _clear_status(console: Console) -> None:
    """Clear the status line."""
    # Move cursor up one line and clear it
    console.print("\033[F\033[K", end="")


def _disable_input() -> tuple:
    """Disable terminal input and return old settings for restoration."""
    try:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        new_settings = termios.tcgetattr(fd)
        # Disable canonical mode and echo
        new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
        termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)
        return (fd, old_settings)
    except Exception as e:
        failures_logger.warning(f"[FAILURE] Failed to disable input: {e}")
        return (None, None)


def _enable_input(settings: tuple) -> None:
    """Restore terminal input settings."""
    fd, old_settings = settings
    if fd is not None and old_settings is not None:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception as e:
            failures_logger.warning(f"[FAILURE] Failed to restore input settings: {e}")


def _render_assistant(console: Console, reply: str) -> None:
    content = (reply or "").rstrip()
    if not content:
        return
    try:
        body = Markdown(content, code_theme="monokai", justify="left")
    except Exception as e:
        failures_logger.warning(f"[FAILURE] Failed to render markdown: {e}")
        body = Text(content)
    panel = Panel.fit(
        body,
        title="[green][ASSISTANT][/]",
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
            f"O {traits_full.get('O','0.00')}  C {traits_full.get('C','0.00')}  "
            f"E {traits_full.get('E','0.00')}  A {traits_full.get('A','0.00')}  "
            f"N {traits_full.get('N','0.00')}",
            style="bold white",
        )
        grid.add_row(tf_line)

    # Deltas (IAS/GAS and commitments) if provided by MetricsView
    deltas = snap.get("deltas") or {}
    try:
        d_ias = deltas.get("IAS_delta")
        d_gas = deltas.get("GAS_delta")
        open_prev = deltas.get("open_prev")
        if d_ias is not None or d_gas is not None or open_prev is not None:
            d_line = Text("Δ ", style="bright_blue")
            if d_ias is not None:
                try:
                    d_line.append("IAS ", style="bright_cyan")
                    d_line.append(
                        ("+" if float(d_ias) >= 0 else "") + f"{float(d_ias):.3f}",
                        style="bold white",
                    )
                except Exception:
                    d_line.append("IAS ?", style="bold white")
                d_line.append("   ")
            if d_gas is not None:
                try:
                    d_line.append("GAS ", style="bright_cyan")
                    d_line.append(
                        ("+" if float(d_gas) >= 0 else "") + f"{float(d_gas):.3f}",
                        style="bold white",
                    )
                except Exception:
                    d_line.append("GAS ?", style="bold white")
                d_line.append("   ")
            if open_prev is not None:
                try:
                    d_line.append("Open commitments ", style="bright_cyan")
                    d_line.append(
                        f"{int(open_prev)}→{open_count} (Δ{open_count - int(open_prev)})",
                        style="bold white",
                    )
                except Exception:
                    pass
            grid.add_row(d_line)
    except Exception:
        pass

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

    memegraph = snap.get("memegraph")
    if isinstance(memegraph, dict) and memegraph:
        mg_line = Text("MemeGraph ", style="bright_magenta")

        def _fmt(val, *, digits: int = 0, fallback: str = "?") -> str:
            try:
                if isinstance(val, float):
                    if digits:
                        return f"{val:.{digits}f}"
                    return f"{val:.0f}"
                if isinstance(val, int):
                    return str(val)
                if isinstance(val, str):
                    return val
                if val is None:
                    return fallback
            except Exception:
                return fallback
            return fallback

        parts = [
            f"nodes {_fmt(memegraph.get('nodes'))}",
            f"edges {_fmt(memegraph.get('edges'))}",
            f"batch {_fmt(memegraph.get('batch_events'))}",
            f"ms {_fmt(memegraph.get('duration_ms'), digits=3)}",
        ]
        rss = memegraph.get("rss_kb")
        if rss is not None:
            parts.append(f"rss_kb {_fmt(rss)}")
        mg_line.append(" | ".join(parts), style="bold white")
        grid.add_row(mg_line)

    # Render deltas (per-turn changes) and signals
    deltas = snap.get("deltas") or {}
    d_ias = deltas.get("IAS_delta")
    d_gas = deltas.get("GAS_delta")
    open_prev = deltas.get("open_prev")
    if d_ias is not None or d_gas is not None or open_prev is not None:
        delta_line = Text("DELTA ", style="bright_yellow")
        parts = []
        if d_ias is not None:
            sign = "+" if float(d_ias) >= 0 else ""
            parts.append(f"ΔIAS={sign}{float(d_ias):.3f}")
        if d_gas is not None:
            sign = "+" if float(d_gas) >= 0 else ""
            parts.append(f"ΔGAS={sign}{float(d_gas):.3f}")
        if open_prev is not None:
            delta_commits = open_count - int(open_prev)
            parts.append(
                f"commitments {int(open_prev)}→{open_count} (Δ{delta_commits})"
            )
        delta_line.append(" | ".join(parts), style="bold white")
        grid.add_row(delta_line)

    # Render signals (commitment scan and identity adoption decisions)
    signals = snap.get("signals") or {}
    commit_sig = signals.get("commitment") or {}
    identity_sig = signals.get("identity") or {}
    if commit_sig or identity_sig:
        sig_line = Text("SIGNALS ", style="bright_cyan")
        sig_parts = []
        if commit_sig:
            status = commit_sig.get("status", "none")
            score = commit_sig.get("best_score", 0.0)
            speaker = commit_sig.get("speaker", "?")
            sig_parts.append(f"commit:{status} score={score:.2f} src={speaker}")
        if identity_sig:
            candidate = identity_sig.get("candidate", "?")
            conf = identity_sig.get("confidence")
            conf_str = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else "?"
            accepted = "yes" if identity_sig.get("accepted") else "no"
            source = identity_sig.get("source", "?")
            sig_parts.append(
                f"identity:{candidate} conf={conf_str} accepted={accepted} src={source}"
            )
        sig_line.append(" | ".join(sig_parts), style="bold white")
        grid.add_row(sig_line)

    return Panel(
        grid,
        title="[blue]METRICS[/]",
        border_style="blue",
        padding=(0, 1),
        box=box.ROUNDED,
    )


def main() -> None:
    # Clear Python bytecode cache on startup to ensure code changes take effect
    # This allows development without external tools or manual cache clearing
    import shutil

    cache_dirs = list(Path(__file__).parent.parent.rglob("__pycache__"))
    for cache_dir in cache_dirs:
        try:
            shutil.rmtree(cache_dir)
        except Exception:
            pass  # Ignore errors, cache clearing is best-effort

    print("[DEBUG] CLI main() started", file=sys.stderr, flush=True)

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
    metrics_view_enabled = False
    metrics_logs_enabled = False
    metrics_logger = logging.getLogger("pmm.runtime.metrics")
    failures_logs_enabled = False
    debug_logs_enabled = False
    debug_logger = logging.getLogger("pmm.runtime.loop")

    runtime.start_autonomy(
        max(0.01, float(env.autonomy_interval or 10)), bootstrap_identity=False
    )

    assistant_console.print(
        _system_panel(
            f"PMM ready ({provider}/{model_name}) — DB: {env.db_path}. Ctrl+C to exit.",
            title="ready",
            border_style="blue",
        )
    )
    assistant_console.print(
        _system_panel(
            "Command reference:\n"
            "  --@metrics on/off      → toggle the live metrics panel\n"
            "  --@metrics             → print a one-time metrics snapshot\n"
            "  --@metrics logs on/off → toggle runtime metrics logging\n"
            "  --@failures on/off     → toggle failure diagnostics\n"
            "  --@debug on/off        → toggle identity/commitment debug logs\n"
            "  --@graph on/off        → inject or suppress graph evidence next turn",
            title="commands",
            border_style="magenta",
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
            user_input = assistant_console.input("\n[bold blue][USER]:[/] ").strip()
            if not user_input:
                continue

            normalized = user_input.strip()
            if normalized == "--@metrics on":
                if not metrics_view_enabled:
                    metrics_view_enabled = True
                    assistant_console.print(
                        _system_panel(
                            "Metrics panel will be shown after each interaction.",
                            title="metrics",
                            border_style="green",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Metrics panel is already enabled.",
                            title="metrics",
                            border_style="cyan",
                        )
                    )
                continue

            if normalized == "--@metrics off":
                if metrics_view_enabled:
                    metrics_view_enabled = False
                    assistant_console.print(
                        _system_panel(
                            "Metrics panel disabled.",
                            title="metrics",
                            border_style="yellow",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Metrics panel is already disabled.",
                            title="metrics",
                            border_style="cyan",
                        )
                    )
                continue

            if normalized == "--@metrics":
                try:
                    snapshot = metrics_view.snapshot(
                        runtime.eventlog, getattr(runtime, "memegraph", None)
                    )
                    assistant_console.print(_metrics_panel(snapshot))
                except Exception as e:
                    logger.debug(f"Unable to load metrics snapshot: {e}")
                    assistant_console.print(
                        _system_panel(
                            "Unable to load metrics snapshot.",
                            title="metrics",
                            border_style="red",
                        )
                    )
                continue

            if normalized == "--@metrics logs on":
                if not metrics_logs_enabled:
                    metrics_logger.setLevel(logging.INFO)
                    metrics_logs_enabled = True
                    assistant_console.print(
                        _system_panel(
                            "Metrics logger set to INFO.",
                            title="metrics",
                            border_style="green",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Metrics logger already at INFO.",
                            title="metrics",
                            border_style="cyan",
                        )
                    )
                continue

            if normalized == "--@metrics logs off":
                if metrics_logs_enabled:
                    metrics_logger.setLevel(logging.WARNING)
                    metrics_logs_enabled = False
                    assistant_console.print(
                        _system_panel(
                            "Metrics logger silenced (WARNING).",
                            title="metrics",
                            border_style="yellow",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Metrics logging already off.",
                            title="metrics",
                            border_style="dim",
                        )
                    )
                continue

            if normalized == "--@failures on":
                if not failures_logs_enabled:
                    failures_logger.setLevel(logging.WARNING)
                    failures_logs_enabled = True
                    assistant_console.print(
                        _system_panel(
                            "Failure diagnostics enabled.",
                            title="failures",
                            border_style="green",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Failure diagnostics already enabled.",
                            title="failures",
                            border_style="cyan",
                        )
                    )
                continue

            if normalized == "--@failures off":
                if failures_logs_enabled:
                    failures_logger.setLevel(logging.ERROR)
                    failures_logs_enabled = False
                    assistant_console.print(
                        _system_panel(
                            "Failure diagnostics disabled.",
                            title="failures",
                            border_style="yellow",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Failure diagnostics already disabled.",
                            title="failures",
                            border_style="dim",
                        )
                    )
                continue

            if normalized == "--@debug on":
                if not debug_logs_enabled:
                    debug_logger.setLevel(logging.DEBUG)
                    debug_logs_enabled = True
                    try:
                        runtime.enable_debug_logging()
                    except AttributeError:
                        pass
                    assistant_console.print(
                        _system_panel(
                            "Debug logging enabled (identity, commitments).",
                            title="debug",
                            border_style="green",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Debug logging already on.",
                            title="debug",
                            border_style="dim",
                        )
                    )
                continue

            if normalized == "--@debug off":
                if debug_logs_enabled:
                    debug_logger.setLevel(logging.WARNING)
                    debug_logs_enabled = False
                    try:
                        runtime.disable_debug_logging()
                    except AttributeError:
                        pass
                    assistant_console.print(
                        _system_panel(
                            "Debug logging disabled.",
                            title="debug",
                            border_style="yellow",
                        )
                    )
                else:
                    assistant_console.print(
                        _system_panel(
                            "Debug logging already off.",
                            title="debug",
                            border_style="dim",
                        )
                    )
                continue

            if normalized in {"--@graph", "--@graph on"}:
                runtime.force_graph_context()
                assistant_console.print(
                    _system_panel(
                        "Graph evidence will be injected on the next turn.",
                        title="graph",
                        border_style="green",
                    )
                )
                continue

            if normalized == "--@graph off":
                runtime.suppress_graph_context()
                assistant_console.print(
                    _system_panel(
                        "Graph evidence suppressed for the next turn.",
                        title="graph",
                        border_style="yellow",
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
                except Exception as e:
                    logger.debug(f"Failed to stop autonomy: {e}")
                return

            # Phase 2.1: Stream response tokens as they're generated
            # Provides 15x faster perceived latency (3000ms → 200ms)
            # Temporarily silence debug logs to prevent interleaving with streaming output
            debug_logger.setLevel(logging.WARNING)
            failures_logger.setLevel(logging.ERROR)
            assistant_console.print("\n[green][ASSISTANT]:[/green] ", end="")
            reply_tokens = []
            try:
                for token in runtime.handle_user_stream(user_input):
                    assistant_console.print(token, end="", highlight=False)
                    reply_tokens.append(token)
                assistant_console.print()  # Newline after complete response
                reply = "".join(reply_tokens)
            except Exception as e:
                failures_logger.warning(
                    f"[FAILURE] Streaming failed, falling back to non-streaming: {e}"
                )
                reply = runtime.handle_user(user_input)
                _render_assistant(assistant_console, reply)
            finally:
                # Restore log levels after streaming completes
                debug_logger.setLevel(
                    logging.DEBUG if debug_logs_enabled else logging.WARNING
                )
                failures_logger.setLevel(
                    logging.WARNING if failures_logs_enabled else logging.ERROR
                )

            # Disable input during processing
            input_settings = _disable_input()

            # Show initial status
            _show_status(assistant_console, "💭 Thinking...")

            # Check for hallucination detection
            try:
                hallucination_ids = getattr(runtime, "_last_hallucination_ids", None)
                if hallucination_ids:
                    _show_status(
                        assistant_console,
                        f"⚠️  Hallucination detected: {hallucination_ids}",
                    )
            except Exception as e:
                logger.debug(f"Failed to check for hallucination detection: {e}")

            # Check for commitment status mismatches
            try:
                status_mismatches = getattr(runtime, "_last_status_mismatches", None)
                if status_mismatches:
                    _show_status(
                        assistant_console, f"⚠️  Status mismatch: {status_mismatches}"
                    )
                    logger.warning(
                        "[bold yellow][status-mismatch][/bold yellow] "
                        f"LLM claimed wrong commitment status: {status_mismatches}"
                    )
            except Exception as e:
                logger.debug(f"Failed to check for commitment status mismatches: {e}")

            try:
                events = runtime.eventlog.read_tail(limit=1000)
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
                    _show_status(assistant_console, "✨ Evolving...")
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
                        except Exception as e:
                            logger.debug(f"Failed to parse cooldown threshold: {e}")
                            cooldown_thr = None
                        break
                prev_thr = getattr(main, "_last_cooldown_thr")
                if cooldown_thr is not None and cooldown_thr != prev_thr:
                    logger.info(
                        "[bold blue][policy][/bold blue] cooldown.novelty_threshold → %.2f",
                        cooldown_thr,
                    )
                    setattr(main, "_last_cooldown_thr", cooldown_thr)
            except Exception as e:
                logger.debug(f"Failed to update stage and cooldown threshold: {e}")

            try:
                events = runtime.eventlog.read_tail(limit=1000)
                last_event = events[-1] if events else None
                if last_event and last_event.get("kind") == "commitment_open":
                    meta = last_event.get("meta") or {}
                    if meta.get("reason") == "reflection":
                        if not hasattr(main, "_last_commitment_id"):
                            setattr(main, "_last_commitment_id", None)
                        prev_cid = getattr(main, "_last_commitment_id")
                        if last_event.get("id") != prev_cid:
                            _show_status(
                                assistant_console, "📊 Analyzing commitments..."
                            )
                            logger.info(
                                "[bold blue][commitment][/bold blue] opened from reflection"
                            )
                            setattr(main, "_last_commitment_id", last_event.get("id"))
            except Exception as e:
                logger.debug(f"Failed to check for commitment opening: {e}")

            try:
                events = runtime.eventlog.read_tail(limit=1000)
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
            except Exception as e:
                logger.debug(f"Failed to check for bridge policy update: {e}")

            try:
                events = runtime.eventlog.read_tail(limit=1000)
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
            except Exception as e:
                logger.debug(f"Failed to check for commitment reminders: {e}")

            try:
                events = runtime.eventlog.read_tail(limit=1000)
                if should_print_identity_notice(events):
                    ident = build_identity(events)
                    name = ident.get("name")
                    if name:
                        logger.info(
                            "[bold blue][identity][/bold blue] adopted name: %s",
                            name,
                        )
            except Exception as e:
                logger.debug(f"Failed to check for identity notice: {e}")

            if metrics_view_enabled:
                try:
                    snapshot = metrics_view.snapshot(
                        runtime.eventlog, getattr(runtime, "memegraph", None)
                    )
                    assistant_console.print(_metrics_panel(snapshot))
                except Exception as e:
                    logger.debug(f"Failed to load metrics snapshot: {e}")

            # Reflection check - show status during check
            try:
                _show_status(assistant_console, "🤔 Reflecting...")
                with profiler.measure("maybe_reflect"):
                    graph = getattr(runtime, "memegraph", None)
                    mirror = (
                        LedgerMirror(runtime.eventlog, graph)
                        if graph is not None
                        else None
                    )
                    runtime_maybe_reflect(
                        runtime.eventlog,
                        runtime.cooldown,
                        mirror=mirror,
                        llm_generate=lambda context: runtime.reflect(context),
                        memegraph=getattr(runtime, "memegraph", None),
                    )
            except Exception as e:
                _show_status(assistant_console, "😕 Hmm, something unexpected...")
                import time

                time.sleep(0.5)
                logger.warning(f"Reflection error: {e}")
            finally:
                # Always clear status before prompt appears
                _clear_status(assistant_console)
                # Re-enable input for next prompt
                _enable_input(input_settings)
    except (EOFError, KeyboardInterrupt):
        assistant_console.print(
            _system_panel("bye.", title="goodbye", border_style="blue")
        )
        try:
            runtime.stop_autonomy()
        except Exception as e:
            logger.debug(f"Failed to stop autonomy: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
