# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

import os
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from pmm.runtime.mcp_server import pmm_turn


def test_pmm_turn_success():
    mock_run = MagicMock()
    # Mocking standard successful run_one_turn stdout JSON
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='{"assistant": "Bridge online", "opened": []}',
        stderr=""
    )

    with patch("subprocess.run", mock_run), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db", "PMM_MCP_MODEL": "ornith:9b"}):

        result = pmm_turn(prompt="Hello", model=None, include_events=False)

        assert result["assistant"] == "Bridge online"
        assert mock_run.called
        
        # Verify default model environment fallback and prompt stdin transmission
        args, kwargs = mock_run.call_args
        cmd = kwargs.get("args") or args[0]
        assert "--db" in cmd
        assert "/path/to/pmm.db" in cmd
        assert "--model" in cmd
        assert "ornith:9b" in cmd
        assert kwargs.get("input") == "Hello"
        assert "--include-events" not in cmd


def test_pmm_turn_model_override():
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(returncode=0, stdout='{"assistant": "ok"}', stderr="")

    with patch("subprocess.run", mock_run), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}):

        # Override model explicitly
        pmm_turn(prompt="Test", model="openai:gpt-4", include_events=True)

        args, kwargs = mock_run.call_args
        cmd = kwargs.get("args") or args[0]
        assert "openai:gpt-4" in cmd
        assert "--include-events" in cmd


def test_pmm_turn_forwards_explicit_output_budget():
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(
        returncode=0, stdout='{"assistant": "ok"}', stderr=""
    )
    with patch("subprocess.run", mock_run), patch.dict(
        os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}
    ):
        pmm_turn(prompt="Test", output_budget_tokens=32)

    cmd = mock_run.call_args.args[0]
    assert cmd[cmd.index("--output-budget-tokens") + 1] == "32"


def test_pmm_turn_rejects_invalid_output_budget_before_subprocess():
    with patch("subprocess.run") as run, patch.dict(
        os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}
    ), pytest.raises(ValueError, match="positive integer"):
        pmm_turn(prompt="Test", output_budget_tokens=0)
    run.assert_not_called()


def test_pmm_turn_forwards_environment_output_budget():
    mock_run = MagicMock()
    mock_run.return_value = MagicMock(
        returncode=0, stdout='{"assistant": "ok"}', stderr=""
    )
    with patch("subprocess.run", mock_run), patch.dict(
        os.environ,
        {
            "PMM_MCP_DB": "/path/to/pmm.db",
            "PMM_OUTPUT_BUDGET_TOKENS": "24",
        },
    ):
        pmm_turn(prompt="Test")

    cmd = mock_run.call_args.args[0]
    assert cmd[cmd.index("--output-budget-tokens") + 1] == "24"


def test_pmm_turn_missing_env():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Environment variable PMM_MCP_DB is required"):
            pmm_turn(prompt="Test")


def test_pmm_turn_nonzero_exit():
    mock_run = MagicMock(
        returncode=1,
        stdout='{"error": "some_error"}',
        stderr="database is locked"
    )

    with patch("subprocess.run", return_value=mock_run), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}):

        with pytest.raises(RuntimeError, match="PMM turn failed \\(exit 1\\): database is locked"):
            pmm_turn(prompt="Test")


def test_pmm_turn_malformed_json():
    mock_run = MagicMock(
        returncode=0,
        stdout="not a json output",
        stderr="runtime warning"
    )

    with patch("subprocess.run", return_value=mock_run), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}):

        with pytest.raises(RuntimeError, match="Failed to parse PMM turn response as JSON"):
            pmm_turn(prompt="Test")


def test_pmm_turn_timeout():
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=240)

    with patch("subprocess.run", side_effect=raise_timeout), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}):

        with pytest.raises(RuntimeError, match="PMM turn execution timed out after 240 seconds"):
            pmm_turn(prompt="Test")


def test_pmm_turn_serialization():
    active_threads = 0
    max_concurrent = 0
    lock_check = threading.Lock()

    def mock_sleep_run(*args, **kwargs):
        nonlocal active_threads, max_concurrent
        with lock_check:
            active_threads += 1
            if active_threads > max_concurrent:
                max_concurrent = active_threads
        time.sleep(0.05)
        with lock_check:
            active_threads -= 1
        return MagicMock(returncode=0, stdout='{"status":"ok"}', stderr="")

    with patch("subprocess.run", side_effect=mock_sleep_run), \
         patch.dict(os.environ, {"PMM_MCP_DB": "/path/to/pmm.db"}):

        threads = []
        for _ in range(5):
            t = threading.Thread(target=lambda: pmm_turn(prompt="hello"))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # The lock MUST serialize calls, meaning max concurrent threads running subprocess.run is exactly 1
        assert max_concurrent == 1
