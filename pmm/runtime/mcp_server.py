# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

# Path: pmm/runtime/mcp_server.py
"""STDIO Model Context Protocol (MCP) server for PMM.

Exposes PMM execution tools to Codex or other MCP-compatible clients.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from pmm.adapters import resolve_output_budget_tokens

# Initialize FastMCP server
mcp = FastMCP("pmm")

# Process-level serialization lock to prevent concurrent turns against the same DB
_turn_lock = threading.Lock()


@mcp.tool()
def pmm_turn(
    prompt: str,
    model: Optional[str] = None,
    include_events: bool = False,
    output_budget_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute a single PMM turn against the configured ledger and return results.

    Arguments:
        prompt: User message prompt for the PMM turn.
        model: Specific model name to target (e.g. 'openai:gpt-4o-mini' or 'ornith:9b').
               Defaults to PMM_MCP_MODEL env variable or 'ornith:9b'.
        include_events: If True, includes full generated event logs in the response.
        output_budget_tokens: Optional provider-enforced generated-token limit.
    """
    db_path = os.environ.get("PMM_MCP_DB")
    if not db_path:
        raise ValueError("Environment variable PMM_MCP_DB is required but not set.")

    default_model = os.environ.get("PMM_MCP_MODEL", "ornith:9b")
    target_model = model or default_model
    resolved_output_budget = resolve_output_budget_tokens(output_budget_tokens)

    cmd = [
        sys.executable,
        "-m",
        "pmm.runtime.oneshot_cli",
        "--db",
        db_path,
        "--model",
        target_model,
    ]
    if include_events:
        cmd.append("--include-events")
    if resolved_output_budget is not None:
        cmd.extend(["--output-budget-tokens", str(resolved_output_budget)])

    # Serialize turns
    with _turn_lock:
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=240,  # 240 seconds timeout
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"PMM turn execution timed out after 240 seconds: {e}")

    if result.returncode != 0:
        err_msg = (result.stderr or "").strip()
        raise RuntimeError(f"PMM turn failed (exit {result.returncode}): {err_msg}")

    try:
        # Standard output contains strictly the JSON payload
        output_json = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        err_msg = (result.stderr or "").strip()
        stdout_excerpt = (result.stdout or "")[:200]
        raise RuntimeError(
            f"Failed to parse PMM turn response as JSON: {e}\n"
            f"Stdout excerpt: {stdout_excerpt}\n"
            f"Stderr: {err_msg}"
        )

    return output_json


if __name__ == "__main__":
    mcp.run()
