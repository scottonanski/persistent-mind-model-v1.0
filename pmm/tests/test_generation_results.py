from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from pmm.adapters import GenerationResult
from pmm.adapters.ollama_adapter import OllamaAdapter
from pmm.core.event_log import EventLog
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.oneshot_cli import run_one_turn
from pmm.runtime.prompts import SYSTEM_PRIMER


class ResultAdapter:
    def __init__(self, result: GenerationResult) -> None:
        self.result = result

    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        return self.result


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"response": "OK", "done": True, "done_reason": "stop"}, "complete"),
        ({"response": "", "done": True, "done_reason": "stop"}, "empty"),
        ({"response": "partial", "done": True, "done_reason": "length"}, "truncated"),
        ({"response": "text", "done": True, "done_reason": "other"}, "indeterminate"),
        ({"response": "text", "done": False}, "indeterminate"),
    ],
)
def test_ollama_classifies_generation_envelope(payload, expected_status) -> None:
    payload = {
        **payload,
        "thinking": "private reasoning",
        "eval_count": 12,
        "prompt_eval_count": 34,
    }
    adapter = OllamaAdapter(model="ornith:test")
    with patch(
        "pmm.adapters.ollama_adapter.request.urlopen",
        return_value=FakeResponse(payload),
    ) as urlopen:
        result = adapter.generate_reply("system", "user")

    assert result.status == expected_status
    assert result.text == payload["response"]
    assert result.meta["thinking_present"] is True
    assert result.meta["thinking_char_count"] == len("private reasoning")
    assert "thinking" not in result.meta
    expected_prompt = f"{SYSTEM_PRIMER}\n\nsystem\nUser: user\nAssistant:"
    request_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert request_body["prompt"] == expected_prompt
    assert result.meta["adapter_system_primer_insertions"] == 1
    assert result.meta["total_assembled_prompt_chars"] == len(expected_prompt)
    assert result.meta["provider_prompt_tokens"] == 34


@pytest.mark.parametrize("status", ["empty", "truncated", "indeterminate"])
def test_failed_generation_cannot_reach_semantic_parsers(status) -> None:
    partial = (
        "Partial visible response\n"
        "COMMIT: must not persist\n"
        'CLAIM:identity_proposal={"token":"identity.Invalid"}\n'
        'REFLECT:{"summary":"must not persist"}'
    )
    adapter = ResultAdapter(
        GenerationResult(
            text=partial,
            status=status,
            meta={
                "provider": "test",
                "done_reason": "length" if status == "truncated" else "stop",
                "thinking_present": True,
                "thinking_char_count": 42,
            },
        )
    )
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)

    events = loop.run_turn("trigger failure")

    failures = [e for e in events if e["kind"] == "generation_failure"]
    assert len(failures) == 1
    assert failures[0]["content"] == partial
    assert failures[0]["meta"]["status"] == status
    assert "thinking" not in failures[0]["meta"]
    forbidden = {
        "assistant_message",
        "commitment_open",
        "commitment_close",
        "claim",
        "identity_adoption",
        "reflection",
        "metrics_turn",
        "concept_bind_event",
        "concept_bind_thread",
    }
    assert not any(e["kind"] in forbidden for e in events)


def test_complete_generation_reaches_normal_processing() -> None:
    adapter = ResultAdapter(
        GenerationResult(
            text="Complete response\nCOMMIT: persist this",
            status="complete",
            meta={"provider": "test", "done_reason": "stop"},
        )
    )
    log = EventLog(":memory:")
    loop = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)

    events = loop.run_turn("trigger success")

    assert any(e["kind"] == "assistant_message" for e in events)
    assert any(e["kind"] == "commitment_open" for e in events)
    assert not any(e["kind"] == "generation_failure" for e in events)


def test_oneshot_exposes_failure_without_assistant_message() -> None:
    adapter = ResultAdapter(
        GenerationResult(
            text="unfinished partial response",
            status="truncated",
            meta={"provider": "test", "done_reason": "length"},
        )
    )

    result = run_one_turn(
        db_path=":memory:",
        prompt="trigger truncation",
        adapter=adapter,
        include_events=True,
    )

    assert result["assistant"] == ""
    assert result["assistant_raw"] == ""
    assert result["generation_status"] == "truncated"
    assert result["generation_failure"]["partial_response"] == (
        "unfinished partial response"
    )
    assert not any(e["kind"] == "assistant_message" for e in result["events"])
