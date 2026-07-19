from __future__ import annotations

import json
import shutil
import threading
from unittest.mock import patch

from pmm.adapters import GenerationResult
from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog, TERMINAL_OUTCOME_PROTOCOL
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalResult
from pmm.runtime.context_renderer import (
    PRIOR_CONVERSATION_MAX_MESSAGE_CHARS,
    render_context_with_metrics,
    render_prior_managed_pair,
)
from pmm.runtime.loop import RuntimeLoop


def _empty_retrieval(**kwargs) -> RetrievalResult:
    return RetrievalResult(
        event_ids=[], relevant_cids=[], active_concepts=[], provenance={}
    )


class SequenceAdapter:
    def __init__(self, replies: list[str]) -> None:
        self._replies = iter(replies)
        self.system_prompts: list[str] = []

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompts.append(system_prompt)
        return next(self._replies)


def _managed_pair(log: EventLog, user_content: str, assistant_content: str):
    user_id = log.append(
        kind="user_message",
        content=user_content,
        meta={"role": "user", "turn_protocol": TERMINAL_OUTCOME_PROTOCOL},
    )
    assistant_id, _ = log.append_terminal_outcome(
        user_event_id=user_id,
        kind="assistant_message",
        content=assistant_content,
        meta={"role": "assistant"},
    )
    return user_id, assistant_id


def test_prior_pair_is_rendered_filtered_bounded_and_non_evidentiary():
    header = json.dumps(
        {
            "intent": "remember",
            "outcome": "done",
            "next": "continue",
            "self_model": "steady",
            "concepts": ["topic.c02"],
        },
        separators=(",", ":"),
    )
    prior_user = "PRIOR-USER-SENTINEL"
    visible_assistant = "PRIOR-ASSISTANT-SENTINEL"
    first_reply = "\n".join(
        [
            header,
            visible_assistant,
            "COMMIT: internal commitment",
            'CLAIM:user_preference={"value":"brief","evidence_events":[]}',
            'REFLECT:{"note":"internal"}',
            "CLAIM:malformed remains conversational",
        ]
    )
    adapter = SequenceAdapter([first_reply, "second reply"])
    log = EventLog(":memory:")
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)

    with patch("pmm.runtime.loop.run_retrieval_pipeline", _empty_retrieval):
        runtime.run_turn(prior_user)
        runtime.run_turn("CURRENT-USER-SENTINEL")

    prompt = adapter.system_prompts[1]
    assert "## Prior Completed Managed Conversation (Non-Evidentiary)" in prompt
    assert prior_user in prompt
    assert visible_assistant in prompt
    assert "CLAIM:malformed remains conversational" in prompt
    assert header not in prompt
    assert "COMMIT: internal commitment" not in prompt
    assert 'CLAIM:user_preference={"value":"brief"' not in prompt
    assert 'REFLECT:{"note":"internal"}' not in prompt
    assert "CURRENT-USER-SENTINEL" not in prompt

    metrics = log.read_by_kind("metrics_turn")[-1]["meta"]["prompt_telemetry"]
    assert metrics["prior_conversation_status"] == "included"
    assert metrics["prior_conversation_pair_count"] == 1
    assert len(metrics["prior_conversation_event_ids"]) == 2
    assert metrics["prior_conversation_truncated_messages"] == 0
    assert metrics["prior_conversation_deduplicated_event_ids"] == []
    assert prior_user not in json.dumps(metrics)
    assert visible_assistant not in json.dumps(metrics)

    selection = log.read_by_kind("retrieval_selection")[-1]
    assert json.loads(selection["content"])["selected"] == []


def test_prior_pair_dereferences_exactly_two_records_and_deduplicates_rendering():
    log = EventLog(":memory:")
    pair = _managed_pair(log, "prior user", "prior assistant")
    meme = MemeGraph(log)
    meme.rebuild(log.read_all())
    original_get = log.get
    calls: list[int] = []

    def tracking_get(event_id: int):
        calls.append(event_id)
        return original_get(event_id)

    # The indexed resolver remains usable even when graph traversal and ledger
    # range APIs are unavailable at lookup time.
    meme.graph = object()  # type: ignore[assignment]
    with (
        patch.object(log, "get", side_effect=tracking_get),
        patch.object(log, "read_all", side_effect=AssertionError("scan")),
        patch.object(log, "read_tail", side_effect=AssertionError("scan")),
        patch.object(log, "read_since", side_effect=AssertionError("scan")),
    ):
        resolved = meme.prior_managed_pair(pair[1] + 1)
        prior = render_prior_managed_pair(
            pair=resolved,
            current_user_id=pair[1] + 1,
            eventlog=log,
            selected_event_ids=list(pair),
        )

    assert calls == [pair[0], pair[1]]
    assert prior.deduplicated_event_ids == pair

    retrieval = RetrievalResult(
        event_ids=list(pair),
        relevant_cids=[],
        active_concepts=[],
        provenance={event_id: {"reasons": ["test"], "scores": {}} for event_id in pair},
    )
    rendered = render_context_with_metrics(
        result=retrieval,
        eventlog=log,
        concept_graph=ConceptGraph(log),
        meme_graph=MemeGraph(log),
        mirror=Mirror(log),
        excluded_evidence_ids=set(prior.deduplicated_event_ids),
    )
    combined = f"{prior.text}\n\n{rendered.text}"
    assert combined.count("prior user") == 1
    assert combined.count("prior assistant") == 1
    assert "## Retrieval Selection Mechanics" in rendered.text
    assert "## Evidence" not in rendered.text


def test_independent_selection_is_preserved_and_deduplication_is_telemetered():
    adapter = SequenceAdapter(["first answer", "second answer"])
    log = EventLog(":memory:")
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)
    calls = 0

    def retrieval(**kwargs) -> RetrievalResult:
        nonlocal calls
        calls += 1
        selected: list[int] = []
        if calls == 2:
            pair = kwargs["meme_graph"].prior_managed_pair(kwargs["user_event"]["id"])
            assert pair is not None
            selected = list(pair)
        return RetrievalResult(
            event_ids=selected,
            relevant_cids=[],
            active_concepts=[],
            provenance={
                event_id: {"reasons": ["test"], "scores": {}} for event_id in selected
            },
        )

    with patch("pmm.runtime.loop.run_retrieval_pipeline", retrieval):
        runtime.run_turn("first question")
        runtime.run_turn("second question")

    selection = json.loads(log.read_by_kind("retrieval_selection")[-1]["content"])
    selected_pair = selection["selected"]
    assert len(selected_pair) == 2
    telemetry = log.read_by_kind("metrics_turn")[-1]["meta"]["prompt_telemetry"]
    assert telemetry["selected_evidence_events"] == 2
    assert telemetry["prior_conversation_deduplicated_event_ids"] == selected_pair
    assert adapter.system_prompts[1].count("first question") == 1
    assert adapter.system_prompts[1].count("first answer") == 1


def test_prior_pair_truncation_is_deterministic_and_visible():
    log = EventLog(":memory:")
    pair = _managed_pair(log, "u" * 2500, "a" * 2500)

    first = render_prior_managed_pair(
        pair=pair,
        current_user_id=pair[1] + 1,
        eventlog=log,
        selected_event_ids=[],
    )
    second = render_prior_managed_pair(
        pair=pair,
        current_user_id=pair[1] + 1,
        eventlog=log,
        selected_event_ids=[],
    )

    assert first == second
    assert first.truncated_messages == 2
    assert first.user_chars == PRIOR_CONVERSATION_MAX_MESSAGE_CHARS
    assert first.assistant_chars == PRIOR_CONVERSATION_MAX_MESSAGE_CHARS
    assert first.text.count("… [truncated]") == 2


def test_live_and_reopened_runtime_render_same_prior_pair(tmp_path):
    live_path = tmp_path / "live.db"
    reopened_path = tmp_path / "reopened.db"
    live_adapter = SequenceAdapter(["first answer", "next answer"])
    live = RuntimeLoop(
        eventlog=EventLog(str(live_path)), adapter=live_adapter, autonomy=False
    )

    with patch("pmm.runtime.loop.run_retrieval_pipeline", _empty_retrieval):
        live.run_turn("first question")
        live.eventlog.close()
        shutil.copyfile(live_path, reopened_path)
        live = RuntimeLoop(
            eventlog=EventLog(str(live_path)), adapter=live_adapter, autonomy=False
        )
        live.run_turn("same boundary question")
        live.eventlog.close()

        reopened_adapter = SequenceAdapter(["next answer"])
        reopened = RuntimeLoop(
            eventlog=EventLog(str(reopened_path)),
            adapter=reopened_adapter,
            autonomy=False,
        )
        reopened.run_turn("same boundary question")
        reopened.eventlog.close()

    live_section = live_adapter.system_prompts[1].split(
        "\n\n## Retrieval Selection Mechanics", 1
    )[0]
    reopened_section = reopened_adapter.system_prompts[0].split(
        "\n\n## Retrieval Selection Mechanics", 1
    )[0]
    assert live_section == reopened_section


def test_tail_only_pair_does_not_expand_claim_evidence_availability():
    adapter = SequenceAdapter(
        [
            "first answer",
            'CLAIM:user_preference={"value":"brief","evidence_events":[1]}',
        ]
    )
    log = EventLog(":memory:")
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)

    with patch("pmm.runtime.loop.run_retrieval_pipeline", _empty_retrieval):
        runtime.run_turn("first question")
        runtime.run_turn("second question")

    assert log.read_by_kind("claim") == []
    failure = next(
        event
        for event in log.read_by_kind("validation_failure")
        if event["meta"].get("source") == "claim_validator"
    )
    assert failure["meta"]["reason_code"] == "EVIDENCE_NOT_SELECTED"


class BlockingAdapter:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def generate_reply(self, system_prompt: str, user_prompt: str) -> GenerationResult:
        self.calls += 1
        if self.calls == 1:
            self.entered.set()
            assert self.release.wait(timeout=2)
        return GenerationResult(text="answer", status="complete", meta={})


def test_runtime_loop_serializes_complete_managed_turns():
    adapter = BlockingAdapter()
    log = EventLog(":memory:")
    runtime = RuntimeLoop(eventlog=log, adapter=adapter, autonomy=False)
    second_attempted = threading.Event()

    def second_turn() -> None:
        second_attempted.set()
        runtime.run_turn("second")

    with patch("pmm.runtime.loop.run_retrieval_pipeline", _empty_retrieval):
        first = threading.Thread(target=lambda: runtime.run_turn("first"))
        second = threading.Thread(target=second_turn)
        first.start()
        assert adapter.entered.wait(timeout=2)
        second.start()
        assert second_attempted.wait(timeout=2)
        second.join(timeout=0.1)

        assert second.is_alive()
        assert len(log.read_by_kind("user_message")) == 1

        adapter.release.set()
        first.join(timeout=2)
        second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    users = log.read_by_kind("user_message")
    assistants = log.read_by_kind("assistant_message")
    assert len(users) == len(assistants) == 2
    assert assistants[1]["meta"]["about_event"] == users[1]["id"]
