from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pmm.adapters import (
    GenerationResult,
    resolve_application_output_budget,
    resolve_output_budget_tokens,
)
from pmm.adapters.ollama_adapter import OllamaAdapter
from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.oneshot_cli import run_one_turn


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class UnsupportedCustomAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "ignored"


class BudgetCapableCustomAdapter:
    supports_output_budget = True

    def __init__(self, budget: int) -> None:
        self.output_budget_tokens = budget
        self.output_budget_source = "argument"

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return "OK"


def test_budget_resolution_precedence_and_validation() -> None:
    with patch.dict(os.environ, {"PMM_OUTPUT_BUDGET_TOKENS": "64"}):
        assert resolve_output_budget_tokens() == 64
        assert resolve_output_budget_tokens(32) == 32

    for value in (0, -1, True, 1.0, "1.5", "abc", " 01 "):
        with pytest.raises(ValueError, match="positive integer"):
            resolve_output_budget_tokens(value)  # type: ignore[arg-type]


def test_application_budget_sources_are_deterministic() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_application_output_budget() == (2048, "pmm_default_v1")
        assert resolve_application_output_budget(4096) == (4096, "argument")
    with patch.dict(os.environ, {"PMM_OUTPUT_BUDGET_TOKENS": "1024"}):
        assert resolve_application_output_budget() == (1024, "environment")
        assert resolve_application_output_budget(4096) == (4096, "argument")


def test_unsupported_custom_adapter_fails_before_ledger_mutation(tmp_path) -> None:
    path = tmp_path / "ledger.db"
    with pytest.raises(ValueError, match="unsupported by selected adapter"):
        run_one_turn(
            db_path=str(path),
            prompt="must not persist",
            adapter=UnsupportedCustomAdapter(),
            output_budget_tokens=8,
        )

    assert EventLog(str(path)).read_all() == []


def test_custom_adapter_is_compatible_when_unset_and_explicit_when_capable() -> None:
    unset = run_one_turn(
        db_path=":memory:",
        prompt="hello",
        adapter=UnsupportedCustomAdapter(),
        include_events=True,
    )
    assert unset["generation_status"] == "complete"
    unset_metrics = next(
        e for e in unset["events"] if e["kind"] == "metrics_turn"
    )
    assert unset_metrics["meta"]["output_telemetry"] == {
        "schema": "output_telemetry.v1",
        "configured_output_budget_tokens": None,
        "output_budget_source": "adapter_capability_unknown",
        "provider_output_tokens": None,
        "provider_reasoning_tokens": None,
        "provider_stop_reason": None,
        "length_limit_reached": False,
    }

    capable = run_one_turn(
        db_path=":memory:",
        prompt="hello",
        adapter=BudgetCapableCustomAdapter(8),
        output_budget_tokens=8,
        include_events=True,
    )
    assert capable["generation_status"] == "complete"
    metrics = next(e for e in capable["events"] if e["kind"] == "metrics_turn")
    assert (
        metrics["meta"]["output_telemetry"]["configured_output_budget_tokens"]
        == 8
    )


def test_ollama_maps_budget_and_reports_conservative_output_telemetry() -> None:
    payload = {
        "response": "partial",
        "done": True,
        "done_reason": "length",
        "eval_count": 8,
        "prompt_eval_count": 20,
    }
    adapter = OllamaAdapter(model="test", output_budget_tokens=8)
    with patch(
        "pmm.adapters.ollama_adapter.request.urlopen",
        return_value=FakeResponse(payload),
    ) as urlopen:
        result = adapter.generate_reply("system", "user")

    body = json.loads(urlopen.call_args.args[0].data.decode())
    assert body["options"] == {"temperature": 0, "num_predict": 8}
    assert result.status == "truncated"
    assert result.meta["configured_output_budget_tokens"] == 8
    assert result.meta["provider_output_tokens"] == 8
    assert result.meta["provider_reasoning_tokens"] is None
    assert result.meta["provider_stop_reason"] == "length"
    assert result.meta["length_limit_reached"] is True


def test_normal_ollama_entry_uses_automatic_default_without_environment() -> None:
    payload = {
        "response": "complete",
        "done": True,
        "done_reason": "stop",
        "eval_count": 2,
        "prompt_eval_count": 20,
    }
    with patch.dict(os.environ, {}, clear=True), patch(
        "pmm.adapters.ollama_adapter.request.urlopen",
        return_value=FakeResponse(payload),
    ) as urlopen:
        result = run_one_turn(
            db_path=":memory:",
            prompt="normal turn",
            provider="ollama",
            model="test",
            include_events=True,
        )

    body = json.loads(urlopen.call_args.args[0].data.decode())
    assert body["options"]["num_predict"] == 2048
    metrics = next(e for e in result["events"] if e["kind"] == "metrics_turn")
    telemetry = metrics["meta"]["output_telemetry"]
    assert telemetry["configured_output_budget_tokens"] == 2048
    assert telemetry["output_budget_source"] == "pmm_default_v1"


def test_direct_adapter_construction_remains_unbudgeted() -> None:
    with patch.dict(os.environ, {}, clear=True):
        adapter = OllamaAdapter(model="test")
    assert adapter.output_budget_tokens is None
    assert adapter.output_budget_source == "not_applicable"


def test_openai_maps_budget_and_completion_usage_including_reasoning() -> None:
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=""), finish_reason="length"
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=8,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=8),
            ),
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    fake_openai = SimpleNamespace(OpenAI=lambda: client)
    with patch.dict(sys.modules, {"openai": fake_openai}):
        from pmm.adapters.openai_adapter import OpenAIAdapter

        result = OpenAIAdapter(model="test", output_budget_tokens=8).generate_reply(
            "system", "user"
        )

    assert captured["max_completion_tokens"] == 8
    assert result.status == "truncated"
    assert result.text == ""
    assert result.meta["provider_output_tokens"] == 8
    assert result.meta["provider_reasoning_tokens"] == 8
    assert result.meta["provider_stop_reason"] == "length"
    assert result.meta["length_limit_reached"] is True


def test_length_limited_output_is_terminal_failure_without_semantics() -> None:
    adapter = BudgetCapableCustomAdapter(8)
    adapter.generate_reply = lambda system_prompt, user_prompt: GenerationResult(
        text="partial\nCOMMIT: forbidden",
        status="truncated",
        meta={
            "configured_output_budget_tokens": 8,
            "provider_output_tokens": 8,
            "provider_reasoning_tokens": None,
            "provider_stop_reason": "length",
            "length_limit_reached": True,
        },
    )
    log = EventLog(":memory:")
    RuntimeLoop(
        eventlog=log,
        adapter=adapter,
        autonomy=False,
        output_budget_tokens=8,
    ).run_turn("long answer")

    assert log.read_by_kind("assistant_message") == []
    assert log.read_by_kind("commitment_open") == []
    failure = log.read_by_kind("generation_failure")[0]
    telemetry = failure["meta"]["output_telemetry"]
    assert telemetry == {
        "schema": "output_telemetry.v1",
        "configured_output_budget_tokens": 8,
        "output_budget_source": "argument",
        "provider_output_tokens": 8,
        "provider_reasoning_tokens": None,
        "provider_stop_reason": "length",
        "length_limit_reached": True,
    }


def test_natural_stop_below_budget_is_successful() -> None:
    adapter = BudgetCapableCustomAdapter(8)
    adapter.generate_reply = lambda system_prompt, user_prompt: GenerationResult(
        text="complete",
        status="complete",
        meta={
            "configured_output_budget_tokens": 8,
            "provider_output_tokens": 2,
            "provider_stop_reason": "stop",
            "length_limit_reached": False,
        },
    )
    log = EventLog(":memory:")
    RuntimeLoop(
        eventlog=log,
        adapter=adapter,
        autonomy=False,
        output_budget_tokens=8,
    ).run_turn("short answer")

    assert len(log.read_by_kind("assistant_message")) == 1
    telemetry = log.read_by_kind("metrics_turn")[0]["meta"]["output_telemetry"]
    assert telemetry["provider_stop_reason"] == "stop"
    assert telemetry["length_limit_reached"] is False
