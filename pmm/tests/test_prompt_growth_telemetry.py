from __future__ import annotations

import json

from pmm.adapters import GenerationResult
from pmm.adapters.openai_adapter import _openai_prompt_tokens
from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.context_renderer import render_context_with_metrics
from pmm.runtime.loop import RuntimeLoop
from pmm.runtime.prompts import SYSTEM_PRIMER


class CaptureAdapter:
    def __init__(self, result: GenerationResult | str) -> None:
        self.result = result
        self.system_prompt = None
        self.user_prompt = None

    def generate_reply(self, system_prompt: str, user_prompt: str):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return self.result


def _telemetry(log: EventLog) -> dict:
    metrics = log.read_by_kind("metrics_turn")
    assert len(metrics) == 1
    return metrics[0]["meta"]["prompt_telemetry"]


def test_renderer_reports_exact_component_character_counts() -> None:
    log = EventLog(":memory:")
    event_id = log.append(kind="test_event", content="evidence body", meta={})
    result = RetrievalResult(
        event_ids=[event_id],
        relevant_cids=[],
        active_concepts=[],
        provenance={event_id: {"reasons": ["test"], "scores": {}}},
    )

    rendered = render_context_with_metrics(
        result=result,
        eventlog=log,
        concept_graph=ConceptGraph(log),
        meme_graph=MemeGraph(log),
        mirror=Mirror(log),
    )

    provenance = rendered.text.split("\n\n## Evidence", 1)[0].split(
        "## Retrieval Selection Mechanics", 1
    )[1]
    provenance = "## Retrieval Selection Mechanics" + provenance
    evidence = "## Evidence" + rendered.text.split("\n\n## Evidence", 1)[1]
    assert rendered.retrieval_provenance_chars == len(provenance)
    assert rendered.raw_evidence_chars == len(evidence)
    assert len(rendered.text) >= len(provenance) + len(evidence)


def test_empty_retrieval_telemetry_and_legacy_adapter_unknowns() -> None:
    adapter = CaptureAdapter("OK")
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False).run_turn("hello")

    telemetry = _telemetry(log)
    assert telemetry["schema"] == "prompt_telemetry.v1"
    assert telemetry["system_primer_insertions"] == 1
    assert telemetry["system_primer_chars"] == len(SYSTEM_PRIMER)
    assert telemetry["system_primer_chars"] == 2112
    assert telemetry["selected_evidence_events"] == 0
    assert telemetry["retrieval_provenance_chars"] > 0
    assert telemetry["raw_evidence_chars"] == 0
    assert telemetry["user_message_chars"] == len("hello")
    assert telemetry["total_assembled_prompt_chars"] is None
    assert telemetry["provider_prompt_tokens"] is None
    assert telemetry["context_window_tokens"] is None


def test_provider_measurements_record_one_primer_without_changing_input() -> None:
    sentinel = "USER-SENTINEL"
    result = GenerationResult(
        text="OK",
        status="complete",
        meta={
            "provider": "test",
            "adapter_system_primer_insertions": 0,
            "total_assembled_prompt_chars": 6015,
            "provider_prompt_tokens": 1942,
            "context_window_tokens": 8192,
        },
    )
    adapter = CaptureAdapter(result)
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False).run_turn(sentinel)

    telemetry = _telemetry(log)
    assert adapter.user_prompt == sentinel
    assert adapter.system_prompt.count(SYSTEM_PRIMER) == 1
    assert telemetry["system_primer_insertions"] == 1
    assert telemetry["system_primer_chars"] == len(SYSTEM_PRIMER)
    assert telemetry["total_assembled_prompt_chars"] == 6015
    assert telemetry["provider_prompt_tokens"] == 1942
    assert telemetry["context_window_tokens"] == 8192
    assert sentinel not in json.dumps(telemetry)

    assistant = log.read_by_kind("assistant_message")[0]
    for transport_field in RuntimeLoop._PROMPT_MEASUREMENT_TRANSPORT_FIELDS:
        assert transport_field not in assistant["meta"]


def test_failed_generation_records_equivalent_private_telemetry() -> None:
    sentinel = "FAILURE-SENTINEL"
    adapter = CaptureAdapter(
        GenerationResult(
            text="partial",
            status="truncated",
            meta={
                "provider": "test",
                "adapter_system_primer_insertions": 0,
                "total_assembled_prompt_chars": 5000,
                "provider_prompt_tokens": 1000,
            },
        )
    )
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False).run_turn(sentinel)

    failures = log.read_by_kind("generation_failure")
    assert len(failures) == 1
    telemetry = failures[0]["meta"]["prompt_telemetry"]
    assert telemetry["system_primer_insertions"] == 1
    assert telemetry["total_assembled_prompt_chars"] == 5000
    assert telemetry["provider_prompt_tokens"] == 1000
    assert sentinel not in json.dumps(telemetry)
    assert log.read_by_kind("metrics_turn") == []
    assert log.read_by_kind("assistant_message") == []


def test_openai_prompt_token_normalization() -> None:
    usage = type("Usage", (), {"prompt_tokens": 321})()
    response = type("Response", (), {"usage": usage})()

    assert _openai_prompt_tokens(response) == 321
    assert _openai_prompt_tokens({"usage": {"prompt_tokens": 654}}) == 654
    assert _openai_prompt_tokens({"usage": {}}) is None


def test_metrics_content_format_remains_backward_compatible() -> None:
    adapter = CaptureAdapter("OK")
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False).run_turn("hello")

    content = log.read_by_kind("metrics_turn")[0]["content"]
    assert content.startswith("provider:dummy,model:")
    assert ",in_tokens:" in content
    assert ",out_tokens:" in content
    assert ",lat_ms:" in content
