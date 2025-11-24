# SPDX-License-Identifier: PMM-1.0
# Copyright (c) 2025 Scott O'Nanski

"""Tests for CTLLookupInjector deterministic query → concept mapping."""

import json
from pmm.core.event_log import EventLog
from pmm.core.concept_graph import ConceptGraph
from pmm.runtime.ctl_injector import CTLLookupInjector


def test_ctl_injector_maps_creator_to_user_identity():
    log = EventLog(":memory:")
    # Define user.identity so the injector can match an existing token.
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "user.identity",
                "concept_kind": "identity",
                "definition": "user identity root",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())

    injector = CTLLookupInjector(cg)

    tokens = injector.extract_tokens("Who is the creator of this system?")

    assert "user.identity" in tokens


def test_ctl_injector_tokenizer_and_suffix_matching_are_deterministic():
    log = EventLog(":memory:")
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "topic.deep-learning",
                "concept_kind": "topic",
                "definition": "dl",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    log.append(
        kind="concept_define",
        content=json.dumps(
            {
                "token": "identity.user",
                "concept_kind": "identity",
                "definition": "user identity",
                "attributes": {},
                "version": "1.0",
            }
        ),
        meta={},
    )
    cg = ConceptGraph(log)
    cg.rebuild(log.read_all())
    injector = CTLLookupInjector(cg)

    toks = injector.extract_tokens("Deep learning systems")
    assert "topic.deep-learning" in toks

    toks2 = injector.extract_tokens("identity? user!")
    assert "identity.user" in toks2
