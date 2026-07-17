from __future__ import annotations

import json
import threading

from pmm.adapters import AdapterTransportError, GenerationResult
from pmm.core.event_log import EventLog, TERMINAL_OUTCOME_PROTOCOL
from pmm.runtime.loop import RuntimeLoop


class CompleteAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        return GenerationResult(text="OK", status="complete", meta={"provider": "test"})


class TypedFailureAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        raise AdapterTransportError(
            "TimeoutError",
            meta={
                "provider": "test",
                "adapter_system_primer_insertions": 0,
                "total_assembled_prompt_chars": 4321,
            },
        )


class OrdinaryFailureAdapter:
    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        raise RuntimeError("secret provider detail")


def _managed_user(log: EventLog, content: str = "managed") -> int:
    return log.append(
        kind="user_message",
        content=content,
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )


def test_success_is_linked_protocol_terminal() -> None:
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=CompleteAdapter(), autonomy=False).run_turn("hello")

    user = log.read_by_kind("user_message")[0]
    assistant = log.read_by_kind("assistant_message")[0]
    assert user["meta"]["turn_protocol"] == TERMINAL_OUTCOME_PROTOCOL
    assert assistant["meta"]["turn_protocol"] == TERMINAL_OUTCOME_PROTOCOL
    assert assistant["meta"]["about_event"] == user["id"]


def test_typed_transport_error_preserves_safe_telemetry() -> None:
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=TypedFailureAdapter(), autonomy=False).run_turn(
        "private prompt"
    )

    user = log.read_by_kind("user_message")[0]
    failure = log.read_by_kind("generation_failure")[0]
    assert failure["meta"]["about_event"] == user["id"]
    assert failure["meta"]["turn_protocol"] == TERMINAL_OUTCOME_PROTOCOL
    assert failure["meta"]["status"] == "transport_error"
    assert failure["meta"]["reason_code"] == "ADAPTER_TRANSPORT_ERROR"
    assert failure["meta"]["error_category"] == "TimeoutError"
    telemetry = failure["meta"]["prompt_telemetry"]
    assert telemetry["total_assembled_prompt_chars"] == 4321
    assert telemetry["provider_prompt_tokens"] is None
    assert "private prompt" not in json.dumps(failure["meta"])


def test_ordinary_adapter_exception_records_runtime_only_telemetry() -> None:
    log = EventLog(":memory:")
    RuntimeLoop(eventlog=log, adapter=OrdinaryFailureAdapter(), autonomy=False).run_turn(
        "private prompt"
    )

    failure = log.read_by_kind("generation_failure")[0]
    assert failure["meta"]["status"] == "transport_error"
    assert failure["meta"]["reason_code"] == "ADAPTER_EXCEPTION"
    assert failure["meta"]["error_category"] == "RuntimeError"
    telemetry = failure["meta"]["prompt_telemetry"]
    assert telemetry["total_assembled_prompt_chars"] is None
    assert telemetry["provider_prompt_tokens"] is None
    assert "secret provider detail" not in json.dumps(failure)


def test_latest_managed_user_and_embedding_are_recovered_once() -> None:
    log = EventLog(":memory:")
    user_id = _managed_user(log)
    log.append(
        kind="embedding_add",
        content=json.dumps({"event_id": user_id}),
        meta={},
    )

    RuntimeLoop(eventlog=log, adapter=CompleteAdapter(), autonomy=False)
    RuntimeLoop(eventlog=log, adapter=CompleteAdapter(), autonomy=False)

    failures = log.read_by_kind("generation_failure")
    assert len(failures) == 1
    assert failures[0]["meta"] == {
        "about_event": user_id,
        "source": "runtime_recovery",
        "status": "interrupted",
        "turn_protocol": TERMINAL_OUTCOME_PROTOCOL,
    }


def test_legacy_and_ambiguous_latest_turns_are_not_recovered() -> None:
    legacy = EventLog(":memory:")
    legacy.append(kind="user_message", content="legacy", meta={"role": "user"})
    RuntimeLoop(eventlog=legacy, adapter=CompleteAdapter(), autonomy=False)
    assert legacy.read_by_kind("generation_failure") == []

    ambiguous = EventLog(":memory:")
    _managed_user(ambiguous)
    ambiguous.append(kind="test_event", content="ambiguous", meta={})
    RuntimeLoop(eventlog=ambiguous, adapter=CompleteAdapter(), autonomy=False)
    assert ambiguous.read_by_kind("generation_failure") == []


def test_existing_terminal_prevents_recovery() -> None:
    log = EventLog(":memory:")
    user_id = _managed_user(log)
    log.append_terminal_outcome(
        user_event_id=user_id,
        kind="generation_failure",
        content="",
        meta={"status": "transport_error"},
    )

    RuntimeLoop(eventlog=log, adapter=CompleteAdapter(), autonomy=False)
    assert len(log.read_by_kind("generation_failure")) == 1


def test_two_connections_racing_recovery_create_one_terminal(tmp_path) -> None:
    path = tmp_path / "ledger.db"
    setup = EventLog(str(path))
    user_id = _managed_user(setup)
    first = EventLog(str(path))
    second = EventLog(str(path))
    barrier = threading.Barrier(2)
    results: list[tuple[int, bool]] = []

    def recover(log: EventLog) -> None:
        barrier.wait()
        results.append(
            log.append_terminal_outcome(
                user_event_id=user_id,
                kind="generation_failure",
                content="",
                meta={"source": "runtime_recovery", "status": "interrupted"},
            )
        )

    threads = [
        threading.Thread(target=recover, args=(first,)),
        threading.Thread(target=recover, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(created for _, created in results) == [False, True]
    assert len(set(event_id for event_id, _ in results)) == 1
    assert len(setup.read_by_kind("generation_failure")) == 1


def test_protocol_uniqueness_does_not_apply_to_legacy_about_event() -> None:
    log = EventLog(":memory:")
    log.append(kind="assistant_message", content="one", meta={"about_event": 7})
    log.append(kind="assistant_message", content="two", meta={"about_event": 7})
    assert len(log.read_by_kind("assistant_message")) == 2
