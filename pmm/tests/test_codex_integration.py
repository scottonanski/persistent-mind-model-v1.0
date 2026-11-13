# SPDX-License-Identifier: PMM-1.0
import asyncio
import sqlite3
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from pmm.core.event_log import EventLog
from pmm.runtime.codex_cli import check_connection, main
from pmm.runtime.mcp_server import pmm_get_event, pmm_read_events, pmm_status


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    with EventLog(str(path)) as elog:
        elog.append(kind="user_message", content="first")
        elog.append(kind="user_message", content="x" * 2500)
        elog.append(kind="user_message", content="third")
    monkeypatch.setenv("PMM_MCP_DB", str(path))
    return path


def test_reads_are_bounded_paginated_and_preserve_full_sources(ledger):
    before = ledger.read_bytes()
    assert pmm_status()["last_event_id"] == 3
    page = pmm_read_events(after_id=0, limit=2)
    assert [e["id"] for e in page["events"]] == [1, 2]
    assert page["events"][1]["content_truncated"]
    assert len(page["events"][1]["content"]) == 2000
    assert pmm_read_events(after_id=page["next_after_id"])["events"][0]["id"] == 3
    assert pmm_read_events(limit=1)["events"][0]["id"] == 3
    assert pmm_read_events(after_id=3)["events"] == []
    assert len(pmm_get_event(2)["content"]) == 2500
    assert pmm_get_event(2)["prev_hash"] == pmm_get_event(1)["hash"]
    with pytest.raises(ValueError, match="does not exist"):
        pmm_get_event(999)
    assert ledger.read_bytes() == before


@pytest.mark.parametrize(
    "args", [{"limit": 0}, {"limit": 101}, {"limit": True}, {"after_id": -1}]
)
def test_read_rejects_invalid_bounds(ledger, args):
    with pytest.raises(ValueError):
        pmm_read_events(**args)


def test_missing_ledger_is_not_created(tmp_path, monkeypatch):
    path = tmp_path / "missing.db"
    monkeypatch.setenv("PMM_MCP_DB", str(path))
    with pytest.raises(sqlite3.OperationalError):
        pmm_status()
    assert not path.exists()


def test_reads_work_while_writer_owns_ledger(ledger):
    with EventLog(str(ledger), writer_role="test") as writer:
        assert pmm_status()["last_event_id"] == 3
        assert pmm_get_event(1)["content"] == "first"
        writer.assert_writer_authority()


def test_real_stdio_managed_turn_and_restart(tmp_path):
    path = tmp_path / "wire.db"
    with EventLog(str(path)):
        pass
    config = {
        "enabled": True,
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "pmm.runtime.mcp_server"],
            "cwd": str(Path(__file__).resolve().parents[2]),
            "env": {"PMM_MCP_DB": str(path), "PMM_MCP_MODEL": "dummy:test"},
        },
    }

    async def run():
        initial = await check_connection(config)
        assert initial["status"] == "ok"
        params = StdioServerParameters(
            **{k: v for k, v in config["transport"].items() if k != "type"}
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                reply = await session.call_tool(
                    "pmm_turn",
                    {"prompt": "Remember the wire test", "include_events": True},
                )
                assert not reply.isError
                data = reply.structuredContent["result"]
                assert data["assistant"].startswith("Echo:")
                assert data["generation_failure"] is None
                assert data["opened"]
                source = next(
                    e for e in data["events"] if e["kind"] == "assistant_message"
                )
                read = await session.call_tool(
                    "pmm_get_event", {"event_id": source["id"]}
                )
                assert (
                    read.structuredContent["result"]["content"] == data["assistant_raw"]
                )
                rejected = await session.call_tool("pmm_read_events", {"limit": 101})
                assert rejected.isError
        restarted = await check_connection(config)
        assert restarted["ledger"]["last_event_id"] > 0

    asyncio.run(asyncio.wait_for(run(), timeout=40))


def test_configure_uses_absolute_paths_and_argument_vector(tmp_path):
    with patch("pmm.runtime.codex_cli.subprocess.run") as run:
        assert (
            main(
                ["configure", "--db", str(tmp_path / "a b.db"), "--model", "dummy:test"]
            )
            == 0
        )
    command = run.call_args.args[0]
    assert command[:4] == ["codex", "mcp", "add", "pmm"]
    assert f"PMM_MCP_DB={tmp_path / 'a b.db'}" in command
    assert command[-3] == sys.executable
    assert run.call_args.kwargs["check"] is True


def test_check_failure_is_nonzero(capsys):
    with patch(
        "pmm.runtime.codex_cli.subprocess.run",
        side_effect=FileNotFoundError("missing codex"),
    ):
        assert main(["check"]) == 1
    assert "missing codex" in capsys.readouterr().err


def test_check_rejects_disabled_server():
    with pytest.raises(ValueError, match="disabled"):
        asyncio.run(check_connection({"enabled": False}))


def test_run_preserves_codex_arguments_and_sets_turn_timeout():
    with patch("pmm.runtime.codex_cli.os.execvp") as execute:
        assert main(["run", "--", "exec", "a prompt with spaces"]) == 0
    assert execute.call_args.args == (
        "codex",
        [
            "codex",
            "-c",
            "mcp_servers.pmm.tool_timeout_sec=300",
            "exec",
            "a prompt with spaces",
        ],
    )
