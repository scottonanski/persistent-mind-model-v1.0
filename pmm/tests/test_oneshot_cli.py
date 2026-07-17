# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

import io
import json
import os
import sys
from hashlib import sha1
from unittest.mock import MagicMock, patch

import pytest
from pmm.core.event_log import EventLog
from pmm.runtime.oneshot_cli import (
    run_one_turn,
    main,
    resolve_provider_and_model,
)


class MockCustomAdapter:
    def __init__(self, reply: str):
        self.reply = reply

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return self.reply


def test_resolve_provider_and_model_rules():
    # 1. Unprefixed model defaults to ollama (ignores env)
    with patch.dict(os.environ, {"PMM_PROVIDER": "openai"}):
        prov, mod = resolve_provider_and_model(model="ornith:9b", provider=None)
        assert prov == "ollama"
        assert mod == "ornith:9b"

    # 2. Prefixed model determines provider
    prov, mod = resolve_provider_and_model(model="openai:gpt-4", provider=None)
    assert prov == "openai"
    assert mod == "gpt-4"

    # 3. Explicit provider takes precedence
    prov, mod = resolve_provider_and_model(model="gpt-4", provider="openai")
    assert prov == "openai"
    assert mod == "gpt-4"

    # 4. Conflicting prefix and provider raises ValueError
    with pytest.raises(ValueError, match="Conflict: Explicit provider"):
        resolve_provider_and_model(model="openai:gpt-4", provider="ollama")

    # 5. Fallback to environment PMM_PROVIDER when neither determines one
    with patch.dict(os.environ, {"PMM_PROVIDER": "openai"}):
        prov, mod = resolve_provider_and_model(model=None, provider=None)
        assert prov == "openai"
        assert mod is None

    # 6. Default fallback to ollama when everything is empty
    with patch.dict(os.environ, {}, clear=True):
        prov, mod = resolve_provider_and_model(model=None, provider=None)
        assert prov == "ollama"
        assert mod is None

    # 7. Unsupported provider raises ValueError
    with pytest.raises(ValueError, match="Unknown or unsupported provider"):
        resolve_provider_and_model(model=None, provider="unsupported")


def test_run_one_turn_basic_extraction():
    log_path = ":memory:"
    text = "test commitment marker"
    cid = sha1(text.encode("utf-8")).hexdigest()[:8]

    # Model reply opens a commitment, issues a valid event_existence claim on user_message (ID 1),
    # and closes the commitment.
    reply = (
        "Standard assistant message.\n"
        f"COMMIT: {text}\n"
        'CLAIM:event_existence={"id":1}\n'
        f"CLOSE: {cid}"
    )

    adapter = MockCustomAdapter(reply)

    result = run_one_turn(
        db_path=log_path,
        prompt="Initial prompt",
        adapter=adapter,
        include_events=False
    )

    # Assert visible response is cleaned correctly
    assert result["assistant"] == "Standard assistant message."
    assert "COMMIT:" in result["assistant_raw"]

    # Assert opened/closed/claims are extracted from newly appended events
    assert cid in result["opened"]
    assert cid in result["closed"]

    # Verify claim is parsed and validated (event_existence of ID 1 exists because it was logged first in run_turn)
    assert len(result["claims"]) == 1
    assert result["claims"][0]["type"] == "event_existence"
    assert result["claims"][0]["data"]["id"] == 1

    # Verify event range keys exist and are populated
    assert result["event_range"]["first"] is not None
    assert result["event_range"]["last"] is not None
    assert "events" not in result


def test_run_one_turn_sqlite_in_memory_preservation():
    adapter = MockCustomAdapter("Response")
    result = run_one_turn(
        db_path=":memory:",
        prompt="Initial prompt",
        adapter=adapter,
        include_events=True
    )
    assert len(result["events"]) > 0


def test_main_cli_stdout_and_stderr_success():
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    with patch("sys.argv", ["pmm-turn", "--db", ":memory:", "--provider", "dummy", "--prompt", "test"]), \
         patch("sys.stdout", stdout_capture), \
         patch("sys.stderr", stderr_capture), \
         patch("sys.exit") as mock_exit:

        main()

        mock_exit.assert_called_with(0)
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()

        # Stdout must contain EXACTLY one parseable JSON document
        parsed = json.loads(stdout_output)
        assert "assistant" in parsed
        assert "events" not in parsed

        # Verify stdout is clean of banners and contains no Rich console color tags
        assert "Persistent Mind Model" not in stdout_output
        assert "\033[" not in stdout_output

        # Verify stderr is completely empty on success
        assert stderr_output == ""


def test_main_cli_stdout_and_stderr_failure():
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    # Triggering error via conflicting arguments
    with patch("sys.argv", ["pmm-turn", "--db", ":memory:", "--model", "openai:gpt-4", "--provider", "ollama", "--prompt", "test"]), \
         patch("sys.stdout", stdout_capture), \
         patch("sys.stderr", stderr_capture), \
         patch("sys.exit") as mock_exit:

        main()

        mock_exit.assert_called_with(1)
        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()

        # Stdout must contain exactly one JSON error document
        parsed = json.loads(stdout_output)
        assert "error" in parsed

        # Stderr must contain the traceback/error diagnostic logging
        assert "Conflict: Explicit provider" in stderr_output


def test_main_cli_stdin_prompt():
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    with patch("sys.argv", ["pmm-turn", "--db", ":memory:", "--provider", "dummy"]), \
         patch("sys.stdin.read", return_value="Stdin Prompt"), \
         patch("sys.stdout", stdout_capture), \
         patch("sys.stderr", stderr_capture), \
         patch("sys.exit") as mock_exit:

        main()
        mock_exit.assert_called_with(0)
        parsed = json.loads(stdout_capture.getvalue())
        assert parsed["assistant_raw"] == "Echo: Stdin Prompt\nCOMMIT: note this item"
        assert stderr_capture.getvalue() == ""
