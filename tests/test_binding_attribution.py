from __future__ import annotations

import json

import pytest

from pmm.core.binding_attribution import binding_attribution_meta
from pmm.core.concept_graph import ConceptGraph
from pmm.core.event_log import EventLog
from pmm.core.meme_graph import MemeGraph
from pmm.core.mirror import Mirror
from pmm.retrieval.pipeline import RetrievalConfig, run_retrieval_pipeline
from pmm.runtime.context_renderer import render_context
from pmm.runtime.loop import RuntimeLoop


class ReplySequenceAdapter:
    def __init__(self, replies: list[str]) -> None:
        self.replies = iter(replies)

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        return next(self.replies)


def _binding_content(*, event_id: int, token: str) -> str:
    return json.dumps(
        {"event_id": event_id, "relation": "relevant_to", "tokens": [token]},
        sort_keys=True,
        separators=(",", ":"),
    )


def test_legacy_unknown_is_projection_only() -> None:
    log = EventLog(":memory:")
    target = log.append(kind="test_event", content="target")
    content = _binding_content(event_id=target, token="topic.legacy")
    binding_id = log.append(
        kind="concept_bind_event", content=content, meta={"source": "old_writer"}
    )

    graph = ConceptGraph(log)
    graph.rebuild()

    attribution = graph.attributions_for_event_binding("topic.legacy", target)[0]
    assert attribution["binding_origin"] == "legacy_unknown"
    assert "binding_origin" not in log.get(binding_id)["meta"]
    assert log.count() == 2


def test_model_declared_origin_is_assistant_event() -> None:
    log = EventLog(":memory:")
    loop = RuntimeLoop(
        eventlog=log,
        adapter=ReplySequenceAdapter(
            ['{"concepts":["memory.persistence"]}\nAnswer.\nCOMMIT: relation']
        ),
        autonomy=False,
    )
    loop.run_turn("Explain memory")

    assistant = log.read_by_kind("assistant_message")[0]
    bindings = log.read_by_kind("concept_bind_event")
    assert bindings
    for binding in bindings:
        assert binding["meta"]["source"] == "active_indexing"
        assert binding["meta"]["binding_origin"] == "model_declared"
        assert binding["meta"]["origin_event_id"] == assistant["id"]

    thread = log.read_by_kind("concept_bind_thread")[0]
    assert thread["meta"]["source"] == "loop"
    assert thread["meta"]["binding_origin"] == "model_declared"
    assert thread["meta"]["origin_event_id"] == assistant["id"]


def test_continuity_fallback_is_runtime_attributed() -> None:
    log = EventLog(":memory:")
    RuntimeLoop(
        eventlog=log,
        adapter=ReplySequenceAdapter(["Answer.\nCOMMIT: relation"]),
        autonomy=False,
    ).run_turn("hello")

    for binding in log.read_by_kind("concept_bind_event"):
        assert binding["meta"]["binding_origin"] == "runtime_continuity_fallback"
        assert "origin_event_id" not in binding["meta"]
    thread = log.read_by_kind("concept_bind_thread")[0]
    assert thread["meta"]["binding_origin"] == "runtime_continuity_fallback"


def test_model_rediscovery_does_not_erase_authorship() -> None:
    log = EventLog(":memory:")
    loop = RuntimeLoop(
        eventlog=log,
        adapter=ReplySequenceAdapter(
            [
                "Answer.\nCOMMIT: same_relation",
                '{"concepts":["identity.continuity"]}\nRefined.\nCOMMIT: same_relation',
            ]
        ),
        autonomy=False,
    )
    loop.run_turn("first")
    loop.run_turn("second")

    opens = log.read_by_kind("commitment_open")
    assert len(opens) == 2
    cid = opens[0]["meta"]["cid"]
    assert opens[1]["meta"]["cid"] == cid

    graph = ConceptGraph(log)
    graph.rebuild()
    attributions = graph.attributions_for_thread_binding("identity.continuity", cid)
    assert {item["binding_origin"] for item in attributions} == {
        "model_declared",
        "runtime_continuity_fallback",
    }
    model = next(
        item for item in attributions if item["binding_origin"] == "model_declared"
    )
    second_assistant = log.read_by_kind("assistant_message")[1]
    assert model["origin_event_id"] == second_assistant["id"]
    assert graph.resolve_concepts_for_cid(cid) == {"identity.continuity"}


def test_model_declared_metadata_requires_assistant_event_id() -> None:
    with pytest.raises(ValueError, match="require origin_event_id"):
        binding_attribution_meta(
            source="assistant",
            binding_origin="model_declared",
            kind="concept_bind_event",
            content="{}",
        )


def test_protocol_v1_rejects_invalid_origin_and_nonassistant_declarer() -> None:
    log = EventLog(":memory:")
    user_id = log.append(kind="user_message", content="user")
    content = _binding_content(event_id=user_id, token="topic.invalid")
    with pytest.raises(ValueError, match="unsupported binding_origin"):
        log.append(
            kind="concept_bind_event",
            content=content,
            meta={
                "source": "test",
                "binding_protocol": "concept_binding_attribution.v1",
                "binding_origin": "invalid",
                "attribution_id": "x",
            },
        )

    meta = binding_attribution_meta(
        source="test",
        binding_origin="model_declared",
        kind="concept_bind_event",
        content=content,
        origin_event_id=user_id,
    )
    with pytest.raises(ValueError, match="assistant_message"):
        log.append(kind="concept_bind_event", content=content, meta=meta)


def test_attribution_preserves_retrieval_and_provider_context() -> None:
    def build(attributed: bool):
        log = EventLog(":memory:")
        user_id = log.append(kind="user_message", content="memory", meta={"role": "user"})
        assistant_id = log.append(
            kind="assistant_message", content="memory persists", meta={"role": "assistant"}
        )
        content = _binding_content(
            event_id=assistant_id, token="memory.persistence"
        )
        meta = {"source": "active_indexing"}
        if attributed:
            meta = binding_attribution_meta(
                source="active_indexing",
                binding_origin="model_declared",
                kind="concept_bind_event",
                content=content,
                origin_event_id=assistant_id,
            )
        log.append(kind="concept_bind_event", content=content, meta=meta)
        graph = ConceptGraph(log)
        graph.rebuild()
        meme = MemeGraph(log)
        meme.rebuild(log.read_all())
        mirror = Mirror(log, listen=False)
        result = run_retrieval_pipeline(
            query_text="memory",
            eventlog=log,
            concept_graph=graph,
            meme_graph=meme,
            config=RetrievalConfig(sticky_concepts=["memory.persistence"]),
            user_event=log.get(user_id),
        )
        context = render_context(
            result=result,
            eventlog=log,
            concept_graph=graph,
            meme_graph=meme,
            mirror=mirror,
        )
        return result, context

    legacy_result, legacy_context = build(False)
    attributed_result, attributed_context = build(True)

    assert attributed_result.event_ids == legacy_result.event_ids
    assert attributed_result.relevant_cids == legacy_result.relevant_cids
    assert attributed_result.active_concepts == legacy_result.active_concepts
    assert attributed_result.provenance == legacy_result.provenance
    assert attributed_context == legacy_context
