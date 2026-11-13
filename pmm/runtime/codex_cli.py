# SPDX-License-Identifier: PMM-1.0
"""Configure and verify Codex CLI's PMM STDIO connection."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise argparse.ArgumentTypeError("server name must use letters, digits, _ or -")
    return value


async def check_connection(config: dict) -> dict:
    """Exercise the actual configured server, not just its registration."""
    if not config.get("enabled", False):
        raise ValueError("PMM MCP registration is disabled")
    transport = config["transport"]
    if transport.get("type") != "stdio":
        raise ValueError("PMM connection check requires a STDIO registration")
    parameters = StdioServerParameters(
        command=transport["command"],
        args=transport.get("args", []),
        env={**os.environ, **(transport.get("env") or {})},
        cwd=transport.get("cwd"),
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            if config.get("enabled_tools") is not None:
                names &= set(config["enabled_tools"])
            names -= set(config.get("disabled_tools") or [])
            required = {"pmm_turn", "pmm_status", "pmm_read_events", "pmm_get_event"}
            if not required <= names:
                raise ValueError(f"Server is missing tools: {sorted(required - names)}")
            status = await session.call_tool("pmm_status", {})
            if status.isError:
                raise RuntimeError(f"PMM status failed: {status.content}")
            ledger = (status.structuredContent or {}).get("result")
            if not isinstance(ledger, dict) or ledger.get("status") != "ok":
                raise ValueError("PMM status returned an unexpected response")
            return {
                "status": "ok",
                "tools": sorted(names),
                "ledger": ledger,
                "model_generation_tested": False,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex", help="Codex CLI executable")
    parser.add_argument(
        "--name", default="pmm", type=_server_name, help="MCP registration name"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    configure = commands.add_parser("configure", help="Register PMM with Codex CLI")
    configure.add_argument("--db", required=True, help="PMM SQLite ledger path")
    configure.add_argument(
        "--model", required=True, help="PMM model, e.g. ollama:llama3"
    )
    commands.add_parser("check", help="Verify the configured MCP server and ledger")
    launch = commands.add_parser("run", help="Launch Codex with PMM's turn timeout")
    launch.add_argument("codex_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == "run":
            forwarded = args.codex_args
            if forwarded[:1] == ["--"]:
                forwarded = forwarded[1:]
            os.execvp(
                args.codex,
                [
                    args.codex,
                    "-c",
                    f"mcp_servers.{args.name}.tool_timeout_sec=300",
                    *forwarded,
                ],
            )
            return 0
        if args.action == "configure":
            if args.db == ":memory:":
                raise ValueError(
                    "Codex integration requires a persistent file-backed ledger"
                )
            db = str(Path(args.db).expanduser().resolve())
            # An absolute module launcher works even when Codex starts elsewhere,
            # including an uninstalled source checkout using this interpreter.
            root = str(Path(__file__).resolve().parents[2])
            launcher = (
                f"import sys; sys.path.insert(0, {root!r}); "
                "from pmm.runtime.mcp_server import mcp; mcp.run()"
            )
            subprocess.run(
                [
                    args.codex,
                    "mcp",
                    "add",
                    args.name,
                    "--env",
                    f"PMM_MCP_DB={db}",
                    "--env",
                    f"PMM_MCP_MODEL={args.model}",
                    "--",
                    sys.executable,
                    "-c",
                    launcher,
                ],
                check=True,
                timeout=30,
            )
            print("Registered. Run pmm-codex check to verify the server and ledger.")
            return 0
        result = subprocess.run(
            [args.codex, "mcp", "get", args.name, "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        config = json.loads(result.stdout)
        report = asyncio.run(asyncio.wait_for(check_connection(config), timeout=30))
        print(json.dumps(report, indent=2))
        return 0
    except Exception as exc:
        # Exception groups from MCP transports retain their actionable leaf cause.
        while getattr(exc, "exceptions", None):
            exc = exc.exceptions[0]
        print(f"PMM Codex connection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
